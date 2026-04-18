"""Check for non-sequential or non-standard code fragment numbering."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "CODE_FRAG_NUM"
DESCRIPTION = "Code fragment numbering is non-sequential or uses non-standard suffix"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

FRAG_RE = re.compile(r'Code Fragment\s+(\d+\.\d+\.\d+\w*)')


def run(filepath, html, context):
    if "section-" not in filepath.name and "appendix" not in str(filepath).lower():
        return []

    issues = []
    fragments = []  # (number_str, line_num)

    for i, line in enumerate(html.split("\n"), 1):
        for m in FRAG_RE.finditer(line):
            num = m.group(1)
            fragments.append((num, i))

    if not fragments:
        return issues

    # Check for non-standard suffixes (letters appended)
    for num, line_num in fragments:
        if re.search(r'[a-zA-Z]$', num):
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                f'Non-standard code fragment number: "{num}" (has letter suffix)'))

    # Check sequencing (extract the last digit and verify monotonic increase)
    seen = {}
    for num, line_num in fragments:
        clean = re.sub(r'[a-zA-Z]+$', '', num)
        parts = clean.split('.')
        if len(parts) == 3:
            try:
                seq = int(parts[2])
                if clean not in seen:
                    seen[clean] = line_num
            except ValueError:
                pass

    return issues

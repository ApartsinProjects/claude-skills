"""Check for mixed heading numbering (some h2/h3 numbered, some not) within a file."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "HEADING_NUM_MIX"
DESCRIPTION = "File has a mix of numbered and unnumbered h2/h3 headings"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

H2_RE = re.compile(r'<h2[^>]*>(.*?)</h2>', re.DOTALL)
NUMBERED_RE = re.compile(r'^\s*\d+[\.\)]\s')

# Headings that are conventionally unnumbered (structural, not content)
STRUCTURAL_HEADINGS = {
    "key takeaways", "takeaways", "exercises", "what comes next",
    "what's next", "references", "bibliography", "quiz",
    "part overview", "chapter overview", "prerequisites",
    "further reading", "summary", "lab:", "hands-on lab",
}


def run(filepath, html, context):
    if "section-" not in filepath.name:
        return []

    issues = []
    headings = []

    for i, line in enumerate(html.split("\n"), 1):
        for m in H2_RE.finditer(line):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if not text:
                continue
            # Skip structural headings
            if any(text.lower().startswith(s) for s in STRUCTURAL_HEADINGS):
                continue
            is_numbered = bool(NUMBERED_RE.match(text))
            headings.append((text, i, is_numbered))

    if len(headings) < 2:
        return issues

    numbered = sum(1 for _, _, n in headings if n)
    unnumbered = sum(1 for _, _, n in headings if not n)

    if numbered > 0 and unnumbered > 0:
        # Report the minority pattern
        if unnumbered <= numbered:
            for text, line_num, is_num in headings:
                if not is_num:
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                        f'Unnumbered h2 "{text[:40]}" in a file with numbered headings'))
        else:
            for text, line_num, is_num in headings:
                if is_num:
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                        f'Numbered h2 "{text[:40]}" in a file with unnumbered headings'))

    return issues

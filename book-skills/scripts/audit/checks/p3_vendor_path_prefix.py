"""Check for inconsistent vendor path prefixes across asset includes."""
import re
from collections import namedtuple, Counter

PRIORITY = "P3"
CHECK_ID = "VENDOR_PATH_PREFIX"
DESCRIPTION = "Inconsistent vendor path prefix (./vendor/ vs vendor/ vs ../vendor/)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match src= or href= attributes that reference a vendor path
VENDOR_REF_RE = re.compile(
    r'(?:src|href)=["\'](\.\./vendor/|\.\/vendor/|vendor/)',
    re.IGNORECASE
)


def run(filepath, html, context):
    issues = []
    # Collect all vendor prefixes used in this file
    prefix_lines = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in VENDOR_REF_RE.finditer(line):
            prefix_lines.append((m.group(1), i, line.strip()[:80]))

    if len(prefix_lines) < 2:
        return issues

    # Count prefixes used in this file
    counts = Counter(p for p, _, _ in prefix_lines)
    if len(counts) <= 1:
        return issues

    # Find the majority prefix within this file
    majority_prefix = counts.most_common(1)[0][0]
    for prefix, line_num, line_preview in prefix_lines:
        if prefix != majority_prefix:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                f'Uses "{prefix}" but majority in this file is '
                f'"{majority_prefix}" ({counts[majority_prefix]} occurrences)'))

    return issues

"""Check for excessive consecutive blank lines in HTML files."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "EXCESSIVE_BLANKS"
DESCRIPTION = "Three or more consecutive blank lines"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TRIPLE_BLANK_RE = re.compile(r'\n\s*\n\s*\n\s*\n')


def run(filepath, html, context):
    issues = []
    # Find runs of 3+ blank lines
    lines = html.split("\n")
    blank_count = 0
    start_line = 0

    for i, line in enumerate(lines, 1):
        if line.strip() == "":
            if blank_count == 0:
                start_line = i
            blank_count += 1
        else:
            if blank_count >= 3:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, start_line,
                    f"{blank_count} consecutive blank lines"))
            blank_count = 0

    return issues

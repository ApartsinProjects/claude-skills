"""Check for unclosed p tags inside prerequisites div (p closed by parent div instead of /p)."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "UNCLOSED_PREREQ_P"
DESCRIPTION = "Unclosed <p> tag inside prerequisites div (missing </p> before </div>)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match prerequisites blocks: <div class="prerequisites">...</div>\n</div>
# The bug is: <p>...text...</div> instead of <p>...text...</p></div>
PREREQ_OPEN_RE = re.compile(r'<div\s+class="prerequisites"', re.IGNORECASE)
P_OPEN_RE = re.compile(r'<p\b', re.IGNORECASE)
P_CLOSE_RE = re.compile(r'</p>', re.IGNORECASE)
DIV_CLOSE_RE = re.compile(r'</div>', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    in_prereq = False
    p_open_line = 0
    p_is_open = False
    depth = 0

    for i, line in enumerate(lines, 1):
        if PREREQ_OPEN_RE.search(line):
            in_prereq = True
            depth = 1
            p_is_open = False
            continue

        if not in_prereq:
            continue

        # Track div nesting
        depth += len(re.findall(r'<div\b', line, re.IGNORECASE))
        div_closes = len(DIV_CLOSE_RE.findall(line))

        # Track p tags
        if P_OPEN_RE.search(line):
            p_is_open = True
            p_open_line = i

        if P_CLOSE_RE.search(line):
            p_is_open = False

        # Check: if we see </div> closing the prereq while a <p> is still open
        if div_closes > 0:
            depth -= div_closes
            if depth <= 0 and p_is_open:
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, p_open_line,
                    f"<p> opened on line {p_open_line} inside .prerequisites is closed by </div> instead of </p>",
                ))
                in_prereq = False
                p_is_open = False
            elif depth <= 0:
                in_prereq = False

    return issues

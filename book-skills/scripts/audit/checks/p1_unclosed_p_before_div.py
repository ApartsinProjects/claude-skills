"""Check for unclosed <p> tags followed by block-level elements (div, figure, table, pre)."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "UNCLOSED_P_TAG"
DESCRIPTION = "Paragraph tag opened but not closed before a block-level element"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

P_OPEN_RE = re.compile(r'<p\b[^>]*>', re.IGNORECASE)
P_CLOSE_RE = re.compile(r'</p>', re.IGNORECASE)
BLOCK_OPEN_RE = re.compile(
    r'<(?:div|figure|table|pre|blockquote|ul|ol|section|header|footer|nav|aside|main|form|fieldset|details|h[1-6])\b',
    re.IGNORECASE,
)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    # Track whether we have an unclosed <p>
    p_open = False
    p_open_line = 0
    in_code = False

    for i, line in enumerate(lines, 1):
        # Skip code blocks to avoid false positives
        if re.search(r'<pre\b', line, re.IGNORECASE):
            in_code = True
        if re.search(r'</pre>', line, re.IGNORECASE):
            in_code = False
            continue
        if in_code:
            continue

        # Count p opens and closes on this line
        opens = len(P_OPEN_RE.findall(line))
        closes = len(P_CLOSE_RE.findall(line))

        if opens > 0 and closes >= opens:
            # Balanced on same line, no problem
            pass
        elif opens > closes:
            p_open = True
            p_open_line = i
        elif closes > 0 and p_open:
            p_open = False

        # Check if a block-level element starts while p is open
        if p_open and BLOCK_OPEN_RE.search(line):
            # Exclude the line where <p> itself was opened (inline content)
            if i != p_open_line:
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, i,
                    f'Block-level element starts at line {i} while <p> from '
                    f'line {p_open_line} is still open'
                ))
                p_open = False  # Reset to avoid cascading reports

    return issues

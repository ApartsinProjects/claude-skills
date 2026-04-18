"""Flag manual syntax-highlighting <span> tags inside <code> blocks that conflict with Prism.js."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "MANUAL_HIGHLIGHT_SPANS"
DESCRIPTION = "Manual <span class='kw|cm|nu|...'> inside <code> blocks conflicts with Prism.js highlighting"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Span classes that look like hand-rolled syntax highlighting
_HIGHLIGHT_CLASSES = re.compile(
    r'<span\s+class="(kw|cm|nu|st|op|fn|co|dt|dv|bn|fl|ch|ot|al|fu|er|wa|cn|sc|ss|vs|va|cf|im|bu|ex|do|an|at|pp|in)">'
)

_CODE_OPEN = re.compile(r"<code\b[^>]*>")
_CODE_CLOSE = re.compile(r"</code>")


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    in_code = False
    code_start = 0

    for i, line in enumerate(lines, 1):
        # Track whether we are inside a <code> block
        if _CODE_OPEN.search(line):
            in_code = True
            code_start = i
        if in_code:
            match = _HIGHLIGHT_CLASSES.search(line)
            if match:
                cls = match.group(1)
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, i,
                    f"Manual highlight <span class=\"{cls}\"> inside <code> block "
                    f"(started line {code_start}); let Prism.js handle highlighting"
                ))
        if _CODE_CLOSE.search(line):
            in_code = False

    return issues

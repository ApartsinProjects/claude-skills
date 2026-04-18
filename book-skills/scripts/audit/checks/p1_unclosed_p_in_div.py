"""Flag <p> tags that are terminated by </div> instead of </p> (malformed nesting)."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "UNCLOSED_P_IN_DIV"
DESCRIPTION = "A <p> tag is closed by </div> instead of </p>, creating malformed HTML"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Pattern: a line that opens a <p> (possibly with content) and ends with </div>
# but does NOT contain </p> before the </div>.
_P_CLOSED_BY_DIV = re.compile(r"<p\b[^>]*>(?:(?!</p>).)*</div>\s*$")


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    for i, line in enumerate(lines, 1):
        if _P_CLOSED_BY_DIV.search(line):
            # Make sure this isn't inside a code block or comment
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("<!--"):
                continue
            if stripped.startswith("#") or stripped.startswith("*"):
                continue
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, i,
                "<p> terminated by </div> instead of </p>; "
                "the paragraph tag is never properly closed"
            ))

    return issues

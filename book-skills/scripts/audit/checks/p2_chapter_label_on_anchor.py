"""Check for class="chapter-label" duplicated on the anchor inside the chapter-label div."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "CHAPTER_LABEL_ON_ANCHOR"
DESCRIPTION = 'class="chapter-label" on <a> inside <div class="chapter-label"> causes style duplication'

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match <a ... class="chapter-label" ...> inside a chapter-label div
PATTERN = re.compile(
    r'<div\s+class="chapter-label">\s*<a\b[^>]*class="chapter-label"',
    re.IGNORECASE | re.DOTALL,
)


def run(filepath, html, context):
    issues = []
    # Flatten to catch patterns spanning line breaks
    for m in PATTERN.finditer(html):
        # Find the line number
        line_num = html[:m.start()].count("\n") + 1
        issues.append(Issue(
            PRIORITY, CHECK_ID, filepath, line_num,
            'class="chapter-label" duplicated on both <div> and inner <a>',
        ))
    return issues

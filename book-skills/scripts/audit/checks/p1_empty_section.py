"""Check for section files with very little content (stub pages)."""
import re
import os
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "EMPTY_SECTION"
DESCRIPTION = "Section page has too little content (likely a stub)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

MAIN_RE = re.compile(r'<main[\s>].*?</main>', re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r'<[^>]+>')

MIN_CONTENT_CHARS = 100


def run(filepath, html, context):
    # Only check section-*.html files
    basename = os.path.basename(filepath)
    if not basename.startswith("section-"):
        return []

    issues = []
    m = MAIN_RE.search(html)
    if not m:
        return []

    main_content = m.group()
    # Strip all HTML tags
    text_only = TAG_RE.sub('', main_content)
    # Count non-whitespace characters
    non_ws = re.sub(r'\s', '', text_only)
    if len(non_ws) < MIN_CONTENT_CHARS:
        # Report on the line where <main> starts
        line_num = html[:m.start()].count("\n") + 1
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
            f'Section has only {len(non_ws)} non-whitespace characters '
            f'(minimum {MIN_CONTENT_CHARS}); likely a stub page'))
    return issues

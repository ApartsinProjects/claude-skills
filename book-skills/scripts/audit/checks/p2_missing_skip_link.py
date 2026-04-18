"""Check for missing skip-to-content link near the top of <body>."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "MISSING_SKIP_LINK"
DESCRIPTION = "Page is missing a skip-to-content link for keyboard/screen-reader users"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

BODY_RE = re.compile(r'<body\b[^>]*>', re.IGNORECASE)
# A skip link is typically an <a> pointing to #main, #content, #main-content, etc.
SKIP_LINK_RE = re.compile(
    r'<a\b[^>]*href=["\']#(?:main|content|main-content|skip)["\'][^>]*>',
    re.IGNORECASE
)


def run(filepath, html, context):
    issues = []
    body_match = BODY_RE.search(html)
    if not body_match:
        return issues

    # Look in the first 50 lines after <body> for a skip link
    body_start = body_match.end()
    after_body = html[body_start:]
    first_chunk_lines = after_body.split("\n")[:50]
    first_chunk = "\n".join(first_chunk_lines)

    if not SKIP_LINK_RE.search(first_chunk):
        body_line = html[:body_start].count("\n") + 1
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, body_line,
            "No skip-to-content link found near top of <body>"))

    return issues

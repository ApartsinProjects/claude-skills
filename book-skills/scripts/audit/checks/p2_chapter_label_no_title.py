"""Check for chapter-label divs missing the chapter title after the number."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "CHAPTER_LABEL_NO_TITLE"
DESCRIPTION = "Chapter label has number but no title (e.g. 'Chapter 18' instead of 'Chapter 18: Title')"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match chapter-label content: expect "Chapter NN: Some Title"
# Flag lines where there is "Chapter NN" followed by end-of-link without a colon and title
CHAPTER_LABEL_RE = re.compile(
    r'class="chapter-label"[^>]*>.*?'
    r'>Chapter\s+(\d+)\s*</a>',
    re.IGNORECASE,
)

# Canonical format: "Chapter NN: Title"
CHAPTER_WITH_TITLE_RE = re.compile(
    r'class="chapter-label"[^>]*>.*?'
    r'>Chapter\s+\d+\s*:\s*\S',
    re.IGNORECASE,
)


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        if 'class="chapter-label"' not in line:
            continue
        m = CHAPTER_LABEL_RE.search(line)
        if m and not CHAPTER_WITH_TITLE_RE.search(line):
            chap_num = m.group(1)
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, i,
                f'"Chapter {chap_num}" label is missing its title '
                f'(expected format: "Chapter {chap_num}: Title Name")',
            ))
    return issues

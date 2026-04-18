"""Check that each chapter index.html has required starter elements.

Every module index should have:
  - A chapter overview paragraph (first substantive paragraph after the header)
  - Learning objectives (div.objectives or list with "objectives" nearby)
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "CHAPTER_STARTER"
DESCRIPTION = "Chapter index missing overview or learning objectives"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

OBJECTIVES_RE = re.compile(r'class="objectives"|Learning Objectives|learning objectives', re.I)
OVERVIEW_RE = re.compile(r'chapter.overview|Chapter Overview|module.overview', re.I)


def run(filepath, html, context):
    issues = []
    book_root = context["book_root"]

    # Only check module index files
    if filepath.name != "index.html":
        return issues
    if "module-" not in str(filepath):
        return issues

    rel = str(filepath.relative_to(book_root))

    if not OBJECTIVES_RE.search(html):
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                            f"{rel} has no learning objectives section"))

    if not OVERVIEW_RE.search(html):
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                            f"{rel} has no chapter overview section"))

    return issues

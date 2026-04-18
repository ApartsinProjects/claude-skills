"""Check for structural content (epigraph, prerequisites) placed outside <main>."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "ORPHAN_CONTENT"
DESCRIPTION = "Structural element appears between </header> and <main> (outside both)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

MAIN_RE = re.compile(r'<main\b')
STRUCTURAL_PATTERNS = [
    ("epigraph", re.compile(r'class="epigraph"')),
    ("prerequisites", re.compile(r'class="prerequisites"')),
    ("callout", re.compile(r'class="callout\b')),
]


def run(filepath, html, context):
    if "section-" not in filepath.name:
        return []

    issues = []
    lines = html.split("\n")

    # Find line of <main>
    main_line = None
    for i, line in enumerate(lines, 1):
        if MAIN_RE.search(line):
            main_line = i
            break

    if not main_line:
        return issues

    # Check for structural elements before <main>
    for i, line in enumerate(lines[:main_line - 1], 1):
        for name, pattern in STRUCTURAL_PATTERNS:
            if pattern.search(line):
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'{name} is outside <main> (between </header> and <main>)'))

    return issues

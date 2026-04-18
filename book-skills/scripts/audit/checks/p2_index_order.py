"""Check that module index.html files follow canonical element ordering.

Canonical order for chapter index pages:
  1. epigraph
  2. illustration (optional)
  3. overview
  4. big-picture (optional callout)
  5. prereqs
  6. objectives
  7. sections-list
  8. whats-next
  9. bibliography (optional)

Also enforces: no fun-note callouts in index files (fun facts belong in sections).
"""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "INDEX_ORDER"
DESCRIPTION = "Module index element out of canonical order or disallowed callout"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Canonical order: element name -> rank
CANONICAL_ORDER = {
    "epigraph": 1,
    "illustration": 2,
    "overview": 3,
    "big-picture": 4,
    "prereqs": 5,
    "objectives": 6,
    "sections-list": 7,
    "whats-next": 8,
    "bibliography": 9,
}

# Patterns to detect structural elements
ELEMENT_PATTERNS = [
    ("epigraph", re.compile(r'class="epigraph"')),
    ("illustration", re.compile(r'<figure\b[^>]*class="illustration"')),
    ("overview", re.compile(r'class="overview"')),
    ("big-picture", re.compile(r'class="callout big-picture"')),
    ("prereqs", re.compile(r'class="prereqs"')),
    ("objectives", re.compile(r'class="objectives"')),
    ("sections-list", re.compile(r'class="sections-list"')),
    ("whats-next", re.compile(r'class="whats-next"')),
    ("bibliography", re.compile(r'class="bibliography"')),
]

DISALLOWED_IN_INDEX = [
    ("callout fun-note", re.compile(r'class="callout fun-note"')),
    ("bare fun-note", re.compile(r'class="fun-note"')),
    ("time-estimate", re.compile(r'class="time-estimate"')),
]


def _line_number(html, pos):
    return html[:pos].count("\n") + 1


def run(filepath, html, context):
    issues = []
    book_root = context["book_root"]

    if filepath.name != "index.html":
        return issues
    if "module-" not in str(filepath):
        return issues

    rel = str(filepath.relative_to(book_root))

    # Detect disallowed callouts
    for name, pattern in DISALLOWED_IN_INDEX:
        for m in pattern.finditer(html):
            line = _line_number(html, m.start())
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                                f"{rel}:{line} disallowed '{name}' callout in index page"))

    # Detect structural elements and check order
    found = []
    for name, pattern in ELEMENT_PATTERNS:
        for m in pattern.finditer(html):
            found.append((m.start(), name, _line_number(html, m.start())))

    found.sort(key=lambda x: x[0])

    # Check pairwise ordering (skip illustration which can repeat)
    max_rank_seen = 0
    max_rank_name = None
    for _, name, line in found:
        rank = CANONICAL_ORDER.get(name, 0)
        if rank < max_rank_seen and name != "illustration":
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                                f"{rel}:{line} '{name}' appears after '{max_rank_name}' "
                                f"(expected order: {max_rank_name} before {name})"))
        if rank > max_rank_seen:
            max_rank_seen = rank
            max_rank_name = name

    return issues

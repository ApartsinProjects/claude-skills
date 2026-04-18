"""Check that each part index.html has required structure and no gaps.

Canonical order for part index pages:
  1. epigraph (optional)
  2. opener illustration (figure.illustration with img)
  3. part-overview
  4. big-picture callout
  5. chapter-cards (one per module directory in the part)
  6. whats-next
  7. footer

Also checks:
  - No fun-notes or non-canonical callouts
  - All module directories have a corresponding chapter-card link
"""
import re
from collections import namedtuple
from pathlib import Path

PRIORITY = "P2"
CHECK_ID = "PART_INDEX"
DESCRIPTION = "Part index missing required element or has structural gap"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

SKIP_DIRS = {"vendor", "node_modules", ".git", "deprecated", "__pycache__",
             "agents", "_archive", "templates"}


def _line_number(html, pos):
    return html[:pos].count("\n") + 1


def run(filepath, html, context):
    issues = []
    book_root = context["book_root"]

    # Only check part-level index files (part-*/index.html)
    if filepath.name != "index.html":
        return issues
    parent = filepath.parent
    if not parent.name.startswith("part-"):
        return issues
    # Skip if this is a module index
    if "module-" in str(filepath):
        return issues

    rel = str(filepath.relative_to(book_root))

    # Check required elements
    if not re.search(r'class="part-overview"', html):
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                            f"{rel} missing part-overview section"))

    if not re.search(r'class="callout big-picture"', html):
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                            f"{rel} missing big-picture callout"))

    if not re.search(r'class="whats-next"', html):
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                            f"{rel} missing whats-next section"))

    # Check for opener illustration
    if not re.search(r'<figure\b[^>]*class="illustration"', html):
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                            f"{rel} missing opener illustration (figure.illustration)"))

    # Check for disallowed callouts
    for m in re.finditer(r'class="(callout fun-note|fun-note)"', html):
        line = _line_number(html, m.start())
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                            f"{rel}:{line} disallowed fun-note in part index"))

    # Check that all module directories have chapter-card links
    module_dirs = sorted([
        d.name for d in parent.iterdir()
        if d.is_dir() and d.name.startswith("module-")
        and not any(s in d.parts for s in SKIP_DIRS)
    ])

    for mod_dir in module_dirs:
        if mod_dir not in html:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                                f"{rel} missing chapter-card for {mod_dir}"))

    # Check element ordering
    elements = []
    order_patterns = [
        ("part-overview", re.compile(r'class="part-overview"')),
        ("big-picture", re.compile(r'class="callout big-picture"')),
        ("whats-next", re.compile(r'class="whats-next"')),
    ]
    for name, pattern in order_patterns:
        m = pattern.search(html)
        if m:
            elements.append((m.start(), name))
    elements.sort()

    RANK = {"part-overview": 1, "big-picture": 2, "whats-next": 3}
    max_rank = 0
    max_name = None
    for _, name in elements:
        rank = RANK[name]
        if rank < max_rank:
            line = _line_number(html, _)
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, 0,
                                f"{rel} '{name}' appears after '{max_name}' "
                                f"(expected: {max_name} before {name})"))
        if rank > max_rank:
            max_rank = rank
            max_name = name

    return issues

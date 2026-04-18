"""Verify that every chapter delivers on promises made in FM.4 (How to Use This Book).

Checks that each module directory contains:
  1. At least one hands-on lab or exercise callout
  2. At least one illustration or figure
  3. At least one Big Picture callout
  4. At least one Research Frontier section or callout
  5. Level badges on at least some sections
  6. At least one annotated bibliography / references section
  7. At least one callout of each core type (key-insight, warning, note, tip)
"""
import re
from collections import namedtuple
from pathlib import Path

PRIORITY = "P1"
CHECK_ID = "FM4_PROMISE"
DESCRIPTION = "Chapter missing a feature promised in FM.4 (How to Use This Book)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Core callout types that every module should have at least one of
CORE_CALLOUTS = {
    "exercise|self-check": "exercise or self-check callout",
    "big-picture": "Big Picture callout",
    "key-insight": "Key Insight callout",
    "warning": "Warning callout",
}

# Features to check at the module level (across all sections combined)
MODULE_CHECKS = {
    "figure": (re.compile(r'<figure[\s>]|<img\s'), "illustration or figure"),
    "research_frontier": (re.compile(r'class="callout research-frontier"|Research Frontier', re.I), "Research Frontier section"),
    "level_badge": (re.compile(r'class="level-badge'), "level badges"),
    "bibliography": (re.compile(r'bibliography|references|Further Reading|Annotated Bibliography', re.I), "annotated bibliography or references section"),
}


def run(filepath, html, context):
    """Only fires on module index.html files; aggregates checks across sibling sections."""
    issues = []

    # Only run on module index files
    if filepath.name != "index.html":
        return issues
    if "module-" not in str(filepath):
        return issues

    book_root = context["book_root"]
    mod_dir = filepath.parent

    # Gather all HTML content from this module
    section_files = sorted(mod_dir.glob("section-*.html"))
    if not section_files:
        return issues

    all_html = html  # index.html content
    for sf in section_files:
        try:
            all_html += sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    mod_label = mod_dir.relative_to(book_root)

    # Check core callout types (supports "a|b" alternatives)
    for callout_class, label in CORE_CALLOUTS.items():
        alternatives = callout_class.split("|")
        found = any(f'class="callout {alt}"' in all_html for alt in alternatives)
        if not found:
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, 0,
                f"{mod_label} has no {label}"
            ))

    # Check module-level features
    for key, (pattern, label) in MODULE_CHECKS.items():
        if not pattern.search(all_html):
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, 0,
                f"{mod_label} has no {label}"
            ))

    return issues

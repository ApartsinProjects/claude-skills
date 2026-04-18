#!/usr/bin/env python3
"""
validate_format.py
==================
Scan all HTML pages in the LLMCourse project for violations of the standard
template and format conventions. Checks chapter index pages, section pages,
part index pages, and appendix pages.

Usage:
    C:\\Python314\\python.exe scripts/validate_format.py
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "__pycache__"}

# ---------------------------------------------------------------------------
# Issue collector
# ---------------------------------------------------------------------------

class Issue:
    __slots__ = ("line", "issue_type", "description")

    def __init__(self, line: int, issue_type: str, description: str):
        self.line = line
        self.issue_type = issue_type
        self.description = description

    def __repr__(self):
        return f"  Line {self.line}: [{self.issue_type}] {self.description}"


# ---------------------------------------------------------------------------
# Helper: classify file type
# ---------------------------------------------------------------------------

def classify_file(path: Path):
    """Return one of: 'part_index', 'chapter_index', 'section', 'other'."""
    rel = path.relative_to(BASE_DIR)
    parts = rel.parts

    # part-*/index.html  (direct child of a part folder)
    if (
        len(parts) == 2
        and parts[0].startswith("part-")
        and parts[1] == "index.html"
    ):
        return "part_index"

    # part-*/module-*/index.html
    if (
        len(parts) == 3
        and parts[0].startswith("part-")
        and parts[1].startswith("module-")
        and parts[2] == "index.html"
    ):
        return "chapter_index"

    # part-*/module-*/section-*.html
    if (
        len(parts) == 3
        and parts[0].startswith("part-")
        and parts[1].startswith("module-")
        and parts[2].startswith("section-")
    ):
        return "section"

    # appendices/appendix-*/index.html
    if (
        len(parts) == 3
        and parts[0] == "appendices"
        and parts[1].startswith("appendix-")
        and parts[2] == "index.html"
    ):
        return "chapter_index"

    # appendices/appendix-*/section-*.html
    if (
        len(parts) == 3
        and parts[0] == "appendices"
        and parts[1].startswith("appendix-")
        and parts[2].startswith("section-")
    ):
        return "section"

    return "other"


# ---------------------------------------------------------------------------
# Check functions (each returns a list of Issues)
# ---------------------------------------------------------------------------

RE_BARE_HEADER = re.compile(r"<header\s*>", re.IGNORECASE)
RE_PROPER_HEADER = re.compile(r'<header\s+class\s*=\s*"chapter-header"', re.IGNORECASE)
RE_NAV_HEADER = re.compile(r'<nav\s+class\s*=\s*"header-nav"', re.IGNORECASE)
RE_BOOK_TITLE_LINK = re.compile(r'class\s*=\s*"book-title-link"', re.IGNORECASE)
RE_TOC_LINK = re.compile(r'class\s*=\s*"toc-link"', re.IGNORECASE)
RE_MAIN_CONTENT = re.compile(r'<main\s+class\s*=\s*"content"', re.IGNORECASE)
RE_DIV_CONTAINER = re.compile(r'<div\s+class\s*=\s*"container"', re.IGNORECASE)
RE_FOOTER_STANDARD = re.compile(
    r'<footer>\s*<p>\s*Fifth Edition,\s*2026\s*&middot;\s*<a\s+href="[^"]*toc\.html"\s*>Contents</a>\s*</p>\s*</footer>',
    re.IGNORECASE | re.DOTALL,
)
RE_FOOTER_TAG = re.compile(r"<footer>", re.IGNORECASE)
RE_INLINE_STYLE_LINK = re.compile(r"<a\s[^>]*\bstyle\s*=\s*\"[^\"]*\"", re.IGNORECASE)
RE_INLINE_STYLE_HEADING = re.compile(r"<h[23]\s[^>]*\bstyle\s*=\s*\"[^\"]*\"", re.IGNORECASE)
RE_INLINE_STYLE_KNOWN_DIV = re.compile(
    r'<div\s+class\s*=\s*"(whats-next|overview|objectives|prereqs|part-overview)[^"]*"[^>]*\bstyle\s*=',
    re.IGNORECASE,
)
RE_INLINE_STYLE_KNOWN_DIV_ALT = re.compile(
    r'<div\s[^>]*\bstyle\s*=[^>]*class\s*=\s*"(whats-next|overview|objectives|prereqs|part-overview)',
    re.IGNORECASE,
)
RE_CALLOUT_H4_TITLE = re.compile(
    r'<div\s+class\s*=\s*"callout[^"]*"[^>]*>[\s\S]{0,200}?<h4>',
    re.IGNORECASE,
)
RE_CALLOUT_DIV_TITLE = re.compile(r'<div\s+class\s*=\s*"callout-title"', re.IGNORECASE)
RE_FUN_NOTE_OPEN = re.compile(r'<div\s+class\s*=\s*"callout\s+fun-note[^"]*"', re.IGNORECASE)
RE_FUN_NOTE_TITLE_OK = re.compile(
    r'<div\s+class\s*=\s*"callout-title">\s*Fun Fact\s*</div>',
    re.IGNORECASE,
)
RE_BIB_OLD_OL = re.compile(r'<ol\s+class\s*=\s*"bib-list"', re.IGNORECASE)
RE_BIB_NEW_CARD = re.compile(r'<div\s+class\s*=\s*"bib-entry-card"', re.IGNORECASE)
RE_PART_LABEL = re.compile(r'<div\s+class\s*=\s*"part-label"', re.IGNORECASE)
RE_OVERVIEW = re.compile(r'<div\s+class\s*=\s*"overview"', re.IGNORECASE)
RE_OBJECTIVES = re.compile(r'<div\s+class\s*=\s*"objectives"', re.IGNORECASE)
RE_PREREQS = re.compile(r'<div\s+class\s*=\s*"prereqs"', re.IGNORECASE)
RE_SECTIONS_LIST = re.compile(r'class\s*=\s*"sections-list"', re.IGNORECASE)
RE_SECTION_CARD = re.compile(r'class\s*=\s*"section-card"', re.IGNORECASE)
RE_WHATS_NEXT = re.compile(r'<div\s+class\s*=\s*"whats-next"', re.IGNORECASE)
RE_WHATS_NEXT_INLINE = re.compile(
    r'<div\s+class\s*=\s*"whats-next"[^>]*\bstyle\s*=',
    re.IGNORECASE,
)
RE_CHAPTER_NAV = re.compile(r'class\s*=\s*"chapter-nav"', re.IGNORECASE)
RE_PART_OVERVIEW = re.compile(r'<div\s+class\s*=\s*"part-overview"', re.IGNORECASE)
RE_CHAPTER_CARD = re.compile(r'<div\s+class\s*=\s*"chapter-card"', re.IGNORECASE)
RE_CROSS_REF = re.compile(r'class\s*=\s*"cross-ref"', re.IGNORECASE)


def _find_line(text: str, pos: int) -> int:
    """Return 1-based line number for a character position in text."""
    return text.count("\n", 0, pos) + 1


def check_all_pages(text: str, lines: list[str]) -> list[Issue]:
    """Checks that apply to every HTML page."""
    issues: list[Issue] = []

    # 1. Header class
    has_proper_header = bool(RE_PROPER_HEADER.search(text))
    if not has_proper_header:
        m = RE_BARE_HEADER.search(text)
        if m:
            issues.append(Issue(
                _find_line(text, m.start()),
                "HEADER_NO_CLASS",
                'Bare <header> without class="chapter-header"',
            ))
        else:
            # No header tag found at all (unusual)
            issues.append(Issue(1, "HEADER_MISSING", "No <header> element found"))

    # 2. Nav with header-nav, book-title-link, toc-link
    if not RE_NAV_HEADER.search(text):
        issues.append(Issue(1, "NAV_MISSING", 'Missing <nav class="header-nav">'))
    if not RE_BOOK_TITLE_LINK.search(text):
        issues.append(Issue(1, "NAV_NO_BOOK_LINK", 'Missing class="book-title-link" in nav'))
    if not RE_TOC_LINK.search(text):
        issues.append(Issue(1, "NAV_NO_TOC_LINK", 'Missing class="toc-link" in nav'))

    # 3. Main wrapper
    if not RE_MAIN_CONTENT.search(text):
        m = RE_DIV_CONTAINER.search(text)
        if m:
            issues.append(Issue(
                _find_line(text, m.start()),
                "MAIN_DIV_CONTAINER",
                'Uses <div class="container"> instead of <main class="content">',
            ))
        else:
            issues.append(Issue(1, "MAIN_MISSING", 'Missing <main class="content"> wrapper'))

    # 4. Footer format
    if not RE_FOOTER_STANDARD.search(text):
        m = RE_FOOTER_TAG.search(text)
        if m:
            issues.append(Issue(
                _find_line(text, m.start()),
                "FOOTER_NONSTANDARD",
                "Footer does not match standard template (Fifth Edition, 2026 with toc.html link)",
            ))
        else:
            issues.append(Issue(1, "FOOTER_MISSING", "No <footer> element found"))

    # 5. Inline styles on <a> tags
    for m in RE_INLINE_STYLE_LINK.finditer(text):
        issues.append(Issue(
            _find_line(text, m.start()),
            "INLINE_STYLE_LINK",
            "Inline style on <a> tag",
        ))

    # 6. Inline styles on h2/h3
    for m in RE_INLINE_STYLE_HEADING.finditer(text):
        issues.append(Issue(
            _find_line(text, m.start()),
            "INLINE_STYLE_HEADING",
            "Inline style on heading (h2 or h3)",
        ))

    # 7. Inline styles on known-class divs
    for m in RE_INLINE_STYLE_KNOWN_DIV.finditer(text):
        issues.append(Issue(
            _find_line(text, m.start()),
            "INLINE_STYLE_DIV",
            f'Inline style on <div class="{m.group(1)}">',
        ))
    for m in RE_INLINE_STYLE_KNOWN_DIV_ALT.finditer(text):
        issues.append(Issue(
            _find_line(text, m.start()),
            "INLINE_STYLE_DIV",
            f'Inline style on <div class="{m.group(1)}"> (style before class)',
        ))

    # 8. Callout boxes: <h4> used instead of <div class="callout-title">
    #    We scan line by line for <h4> inside a callout context.
    in_callout = False
    for i, line in enumerate(lines, 1):
        if re.search(r'<div\s+class\s*=\s*"callout\b', line, re.IGNORECASE):
            in_callout = True
        if in_callout and "<h4>" in line.lower():
            # Check if this <h4> is serving as the callout title
            # (i.e., the first non-whitespace content after the callout div)
            issues.append(Issue(
                i,
                "CALLOUT_H4_TITLE",
                "Callout uses <h4> for title instead of <div class=\"callout-title\">",
            ))
        if in_callout and ("</div>" in line and "<div" not in line):
            in_callout = False

    # 9. Fun-note callouts must have proper callout-title
    for m in RE_FUN_NOTE_OPEN.finditer(text):
        # Look ahead up to 500 chars for the callout-title
        window = text[m.start():m.start() + 500]
        if not RE_FUN_NOTE_TITLE_OK.search(window):
            issues.append(Issue(
                _find_line(text, m.start()),
                "FUN_NOTE_NO_TITLE",
                'Fun-note callout missing <div class="callout-title">Fun Fact</div>',
            ))

    # 10. Bibliography: old ol.bib-list pattern
    for m in RE_BIB_OLD_OL.finditer(text):
        issues.append(Issue(
            _find_line(text, m.start()),
            "BIB_OLD_FORMAT",
            'Bibliography uses <ol class="bib-list"> instead of <div class="bib-entry-card"> pattern',
        ))

    # 11. Cross-references: links to other chapters/sections that lack class="cross-ref"
    #     We look for <a href="..."> where the href points to another module/section
    #     but does not have class="cross-ref".
    cross_ref_pattern = re.compile(
        r'<a\s+([^>]*)href\s*=\s*"([^"]*(?:module-|section-|appendix-)[^"]*\.html[^"]*)"([^>]*)>',
        re.IGNORECASE,
    )
    for m in cross_ref_pattern.finditer(text):
        attrs = m.group(1) + m.group(3)
        href = m.group(2)
        # Skip if it is a relative link to the same module (e.g., "section-0.2.html")
        # Only flag links that navigate to a different module directory
        if "/" not in href:
            continue
        if "cross-ref" not in attrs:
            issues.append(Issue(
                _find_line(text, m.start()),
                "CROSS_REF_NO_CLASS",
                f'Cross-reference link missing class="cross-ref": href="{href[:80]}"',
            ))

    return issues


def check_chapter_index(text: str, lines: list[str]) -> list[Issue]:
    """Extra checks for chapter index pages (part-*/module-*/index.html)."""
    issues: list[Issue] = []

    # 12. Must have part-label
    if not RE_PART_LABEL.search(text):
        issues.append(Issue(1, "CH_NO_PART_LABEL", 'Missing <div class="part-label"> in chapter index'))

    # 13. Must have overview
    if not RE_OVERVIEW.search(text):
        issues.append(Issue(1, "CH_NO_OVERVIEW", 'Missing <div class="overview"> section'))

    # 14. Must have objectives
    if not RE_OBJECTIVES.search(text):
        issues.append(Issue(1, "CH_NO_OBJECTIVES", 'Missing <div class="objectives"> section'))

    # 15. Must have prereqs
    if not RE_PREREQS.search(text):
        issues.append(Issue(1, "CH_NO_PREREQS", 'Missing <div class="prereqs"> section'))

    # 16. Must have sections-list with section-card links
    if not RE_SECTIONS_LIST.search(text):
        issues.append(Issue(1, "CH_NO_SECTIONS_LIST", 'Missing sections-list (class="sections-list")'))
    if not RE_SECTION_CARD.search(text):
        issues.append(Issue(1, "CH_NO_SECTION_CARDS", 'Missing section-card links (class="section-card")'))

    # 17. Must have whats-next div (without inline styles)
    if not RE_WHATS_NEXT.search(text):
        issues.append(Issue(1, "CH_NO_WHATS_NEXT", 'Missing <div class="whats-next">'))
    else:
        m = RE_WHATS_NEXT_INLINE.search(text)
        if m:
            issues.append(Issue(
                _find_line(text, m.start()),
                "CH_WHATS_NEXT_INLINE",
                'Whats-next div has inline styles',
            ))

    # 18. Should have chapter-nav at bottom
    if not RE_CHAPTER_NAV.search(text):
        issues.append(Issue(1, "CH_NO_CHAPTER_NAV", 'Missing chapter-nav at bottom'))

    return issues


def check_part_index(text: str, lines: list[str]) -> list[Issue]:
    """Extra checks for part index pages (part-*/index.html)."""
    issues: list[Issue] = []

    # 19. Must have part-overview
    if not RE_PART_OVERVIEW.search(text):
        issues.append(Issue(1, "PART_NO_OVERVIEW", 'Missing <div class="part-overview">'))

    # 20. Must have chapter-card divs
    if not RE_CHAPTER_CARD.search(text):
        issues.append(Issue(1, "PART_NO_CHAPTER_CARDS", 'Missing <div class="chapter-card"> for chapters'))

    # 21. Must have whats-next div
    if not RE_WHATS_NEXT.search(text):
        issues.append(Issue(1, "PART_NO_WHATS_NEXT", 'Missing <div class="whats-next">'))

    return issues


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_html_files(base: Path) -> list[Path]:
    """Find all HTML files, excluding certain directories."""
    results = []
    for html_file in sorted(base.rglob("*.html")):
        # Skip excluded directories
        if any(excl in html_file.parts for excl in EXCLUDE_DIRS):
            continue
        # Skip top-level files that are not part of the book structure
        # (e.g., index.html at root is fine, but we focus on part/module/appendix)
        rel = html_file.relative_to(base)
        first = rel.parts[0] if rel.parts else ""
        if first.startswith("part-") or first == "appendices" or first == "front-matter":
            results.append(html_file)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    html_files = find_html_files(BASE_DIR)
    if not html_files:
        print(f"No HTML files found under {BASE_DIR}")
        sys.exit(1)

    all_issues: dict[Path, list[Issue]] = {}
    type_counts: dict[str, int] = defaultdict(int)
    clean_files: list[Path] = []
    dirty_files: list[Path] = []

    for fpath in html_files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"WARNING: Could not read {fpath}: {e}")
            continue

        lines = text.splitlines()
        ftype = classify_file(fpath)
        issues = check_all_pages(text, lines)

        if ftype == "chapter_index":
            issues.extend(check_chapter_index(text, lines))
        elif ftype == "part_index":
            issues.extend(check_part_index(text, lines))

        if issues:
            all_issues[fpath] = issues
            dirty_files.append(fpath)
            for iss in issues:
                type_counts[iss.issue_type] += 1
        else:
            clean_files.append(fpath)

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    total_issues = sum(type_counts.values())
    total_files = len(html_files)

    print("=" * 78)
    print("  LLMCourse Format Validation Report")
    print("=" * 78)
    print(f"\nScanned {total_files} HTML files in {BASE_DIR}")
    print(f"Found {total_issues} issue(s) across {len(dirty_files)} file(s).\n")

    # Issues grouped by file
    if all_issues:
        print("-" * 78)
        print("  ISSUES BY FILE")
        print("-" * 78)
        for fpath in sorted(all_issues.keys()):
            rel = fpath.relative_to(BASE_DIR)
            file_issues = all_issues[fpath]
            print(f"\n{rel}  ({len(file_issues)} issue(s))")
            for iss in sorted(file_issues, key=lambda i: i.line):
                print(f"  Line {iss.line:>4}: [{iss.issue_type}] {iss.description}")

    # Summary by issue type
    print("\n" + "-" * 78)
    print("  SUMMARY BY ISSUE TYPE")
    print("-" * 78)
    for itype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {count:>5}  {itype}")
    print(f"  {'':->5}  {'':->40}")
    print(f"  {total_issues:>5}  TOTAL")

    # Clean vs dirty
    print("\n" + "-" * 78)
    print("  FILE STATUS")
    print("-" * 78)
    print(f"\n  Clean files (0 issues): {len(clean_files)}")
    for f in sorted(clean_files):
        print(f"    [OK] {f.relative_to(BASE_DIR)}")

    print(f"\n  Files needing attention: {len(dirty_files)}")
    for f in sorted(dirty_files):
        count = len(all_issues[f])
        print(f"    [{count:>3}] {f.relative_to(BASE_DIR)}")

    print("\n" + "=" * 78)
    print(f"  Done. {len(clean_files)} clean, {len(dirty_files)} need attention.")
    print("=" * 78)

    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()

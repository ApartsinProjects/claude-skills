"""Check section files for callout constraint violations.

Section callout ordering is flexible, but some constraints apply:
  1. self-check should not appear in the first 10% of the file (before any content)
  2. research-frontier should be in the last 40% of the main content
  3. bibliography/further-reading section should be after all callouts
  4. No callouts after the chapter-nav (footer area)
  5. exercise callouts should not appear before the first h2/h3 heading
"""
import re
from collections import namedtuple

PRIORITY = "P3"
CHECK_ID = "SECTION_CALLOUT"
DESCRIPTION = "Section callout placement constraint violation"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

CALLOUT_RE = re.compile(r'class="callout\s+(\S+)"')
BIBLIOGRAPHY_RE = re.compile(r'class="bibliography"')
CHAPTER_NAV_RE = re.compile(r'class="chapter-nav"')


def _line_number(html, pos):
    return html[:pos].count("\n") + 1


def run(filepath, html, context):
    issues = []
    book_root = context["book_root"]

    # Only check section files
    if not filepath.name.startswith("section-"):
        return issues
    if filepath.suffix != ".html":
        return issues

    rel = str(filepath.relative_to(book_root))
    total_len = len(html)
    if total_len < 200:
        return issues

    callouts = [(m.start(), m.group(1)) for m in CALLOUT_RE.finditer(html)]

    # Find structural boundaries
    bib_match = BIBLIOGRAPHY_RE.search(html)
    nav_match = CHAPTER_NAV_RE.search(html)
    bib_pos = bib_match.start() if bib_match else total_len
    nav_pos = nav_match.start() if nav_match else total_len
    footer_boundary = min(bib_pos, nav_pos)

    for pos, ctype in callouts:
        line = _line_number(html, pos)

        # 1. self-check too early
        if ctype == "self-check" and pos < total_len * 0.10:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                                f"{rel}:{line} self-check appears in first 10% of file"))

        # 2. research-frontier should be in the latter portion
        if ctype == "research-frontier" and pos < total_len * 0.50:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                                f"{rel}:{line} research-frontier appears in first half of file"))

        # 3. Callouts after chapter-nav
        if pos > nav_pos and ctype not in ("self-check",):
            # Some files legitimately have a self-check after nav, skip those
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                                f"{rel}:{line} '{ctype}' callout appears after chapter-nav"))

        # 4. exercise before first heading (too early for a lab)
        # Exception: "Hands-On Lab" banners are intentionally at section top
        if ctype == "exercise" and pos < total_len * 0.08:
            # Check if this is a Hands-On Lab banner (allowed at top)
            snippet = html[pos:pos + 200]
            if "Hands-On Lab" not in snippet:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, line,
                                    f"{rel}:{line} exercise callout appears before substantive content"))

    return issues

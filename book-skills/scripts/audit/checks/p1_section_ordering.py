"""Check that structural elements appear in the canonical order within section files.

Canonical order (top to bottom of <main>):
  1. epigraph
  2. prerequisites
  3. big-picture callout
  4. body content (headings, paragraphs, code, figures, callouts)
  5. whats-next
  6. bibliography
  7. chapter-nav
  8. footer

Violations reported:
  - Prerequisites after big-picture
  - Big-picture buried deep in content (more than 200 lines from <main>)
  - Callout or heading after bibliography
  - Whats-next after bibliography
  - Content (callouts, code, headings) between whats-next and bibliography
  - Content after whats-next when no bibliography exists
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "SECTION_ORDER"
DESCRIPTION = "Structural elements appear out of canonical order"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

MARKERS = [
    ("epigraph", re.compile(r'class="epigraph"')),
    ("prerequisites", re.compile(r'class="prerequisites"')),
    ("big-picture", re.compile(r'class="callout big-picture"')),
    ("whats-next", re.compile(r'class="whats-next"')),
    ("bibliography", re.compile(r'class="bibliography"')),
    ("chapter-nav", re.compile(r'class="chapter-nav"')),
]

CALLOUT_RE = re.compile(r'<div\s+class="callout\s')
HEADING_RE = re.compile(r'<h[23]\b')
CODE_RE = re.compile(r'<pre\b')


def _find_first_line(html_lines, pattern):
    for i, line in enumerate(html_lines, 1):
        if pattern.search(line):
            return i
    return None


def run(filepath, html, context):
    # Only check section files
    if "section-" not in filepath.name:
        return []

    issues = []
    lines = html.split("\n")

    positions = {}
    for name, pattern in MARKERS:
        pos = _find_first_line(lines, pattern)
        if pos:
            positions[name] = pos

    # Check: prerequisites should come before big-picture
    if "prerequisites" in positions and "big-picture" in positions:
        if positions["prerequisites"] > positions["big-picture"]:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath,
                positions["prerequisites"],
                "Prerequisites appears after big-picture callout (swap them)"))

    # Check: big-picture should be within first 100 lines of <main>,
    # unless it is in the last 40% of the file (end-of-section summary pattern)
    main_line = _find_first_line(lines, re.compile(r'<main\b'))
    if "big-picture" in positions and main_line:
        offset = positions["big-picture"] - main_line
        position_pct = positions["big-picture"] / len(lines) * 100
        if offset > 100 and position_pct < 40:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath,
                positions["big-picture"],
                f"Big-picture callout is {offset} lines into content (should be near top)"))

    # Check: nothing should come after bibliography except nav/footer/whats-next
    bib_line = positions.get("bibliography")
    if bib_line:
        # Find the end of the bibliography div to skip internal headings
        bib_end = bib_line
        depth = 0
        for i in range(bib_line - 1, len(lines)):
            depth += lines[i].count('<div')
            depth -= lines[i].count('</div')
            if depth <= 0 and i > bib_line - 1:
                bib_end = i + 1
                break

        # Bibliography-related heading patterns to exclude
        bib_heading_re = re.compile(
            r'(References|Bibliography|Further Reading|Foundational Papers|'
            r'Tools and Frameworks|Annotated Bibliography|Exercises)',
            re.IGNORECASE
        )

        for i in range(bib_end, len(lines)):
            line_text = lines[i]
            line_num = i + 1
            if CALLOUT_RE.search(line_text):
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                    "Callout appears after bibliography"))
            if HEADING_RE.search(line_text) and "chapter-nav" not in line_text:
                # Exclude headings that are part of whats-next
                if not re.search(r'class="whats-next"', line_text):
                    heading_text = re.sub(r'<[^>]+>', '', line_text).strip()[:50]
                    if heading_text and not bib_heading_re.search(heading_text):
                        issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                            f'Heading after bibliography: "{heading_text}"'))

    # Check: whats-next should come before bibliography
    if "whats-next" in positions and "bibliography" in positions:
        if positions["whats-next"] > positions["bibliography"]:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath,
                positions["whats-next"],
                "Whats-next appears after bibliography (should precede it)"))

    # Check: no content (callouts, code, headings) between whats-next and bibliography
    wn_line = positions.get("whats-next")
    if wn_line and bib_line and wn_line < bib_line:
        # Find end of whats-next div
        wn_end = wn_line
        depth = 0
        for i in range(wn_line - 1, len(lines)):
            depth += lines[i].count('<div')
            depth -= lines[i].count('</div')
            if depth <= 0 and i > wn_line - 1:
                wn_end = i + 2  # line after closing div
                break

        for i in range(wn_end, bib_line - 1):
            line_text = lines[i]
            line_num = i + 1
            if CALLOUT_RE.search(line_text):
                callout_class = re.search(r'class="callout\s+([^"]+)"', line_text)
                ctype = callout_class.group(1) if callout_class else "unknown"
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                    f'Callout ({ctype}) appears between whats-next and bibliography (move before whats-next)'))
            if HEADING_RE.search(line_text):
                heading_text = re.sub(r'<[^>]+>', '', line_text).strip()[:50]
                if heading_text:
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                        f'Heading between whats-next and bibliography: "{heading_text}" (move before whats-next)'))
            if CODE_RE.search(line_text):
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                    "Code block between whats-next and bibliography (move before whats-next)"))

    # Check: no content (callouts, code, headings) after whats-next when no bibliography
    if wn_line and not bib_line:
        nav_line = positions.get("chapter-nav", len(lines))
        wn_end = wn_line
        depth = 0
        for i in range(wn_line - 1, len(lines)):
            depth += lines[i].count('<div')
            depth -= lines[i].count('</div')
            if depth <= 0 and i > wn_line - 1:
                wn_end = i + 2
                break

        for i in range(wn_end, nav_line - 1):
            line_text = lines[i]
            line_num = i + 1
            if CALLOUT_RE.search(line_text):
                callout_class = re.search(r'class="callout\s+([^"]+)"', line_text)
                ctype = callout_class.group(1) if callout_class else "unknown"
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                    f'Callout ({ctype}) appears after whats-next (move before whats-next)'))

    return issues

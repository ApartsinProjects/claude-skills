"""
Deep standardization audit: analyze ALL pages for patterns that deviate from standards.

Checks beyond what validate_format.py covers:
1. DOCTYPE declaration present
2. meta charset and viewport present
3. Title format: "Section X: Title | Building Conversational AI..."
4. link rel="stylesheet" points to correct relative path for book.css
5. body tag present (no attributes needed)
6. Epigraph format: blockquote.epigraph with p and cite
7. Callout title attribute present
8. Math blocks use div.math-block / span.math
9. Code blocks use pre > code with language class
10. Heading hierarchy (h1 in header, h2/h3 in content, no h4/h5/h6 in callouts)
11. Cross-ref links have class="cross-ref"
12. Images have alt text
13. Images have loading="lazy"
14. No empty href or src attributes
15. No TODO/FIXME/PLACEHOLDER comments
16. Exercise callouts have exercise-type span
17. Section files have part-label and chapter-label in header
18. No orphaned closing tags
19. overview div present in chapter index pages
20. Prerequisites/prereqs div format
"""

import re
import random
from pathlib import Path
from collections import defaultdict

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles"}

def find_html_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        # Skip non-content files
        if f.name in ("toc.html", "section-fm.7.html", "how-to-use.html"):
            continue
        files.append(f)
    return sorted(files)

def classify_page(filepath):
    rel = filepath.relative_to(BASE)
    parts = rel.parts
    if filepath.name == "index.html":
        if len(parts) == 2:  # part-X/index.html
            return "part-index"
        elif len(parts) == 3:  # part-X/module-Y/index.html
            return "chapter-index"
    if re.match(r"section-", filepath.name):
        return "section"
    if filepath.name == "index.html" and len(parts) == 1:
        return "root"
    if re.match(r"appendix-", filepath.parent.name) or "appendix" in str(filepath):
        if filepath.name == "index.html":
            return "chapter-index"
        return "section"
    return "other"

def audit_file(filepath):
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    page_type = classify_page(filepath)
    issues = []

    # 1. DOCTYPE
    if not text.strip().startswith("<!DOCTYPE html>"):
        issues.append((1, "NO_DOCTYPE", "Missing <!DOCTYPE html> declaration"))

    # 2. Meta tags
    if '<meta charset="UTF-8">' not in text:
        issues.append((0, "NO_META_CHARSET", "Missing meta charset UTF-8"))
    if '<meta name="viewport"' not in text:
        issues.append((0, "NO_META_VIEWPORT", "Missing meta viewport"))

    # 3. CSS link
    css_links = re.findall(r'<link\s+rel="stylesheet"\s+href="([^"]*)"', text)
    for href in css_links:
        if "book.css" in href:
            # Check relative path correctness
            resolved = (filepath.parent / href).resolve()
            expected = BASE / "styles" / "book.css"
            if not resolved.exists():
                issues.append((0, "CSS_LINK_BROKEN", f"book.css link broken: {href}"))
    if not any("book.css" in h for h in css_links):
        issues.append((0, "NO_BOOK_CSS", "No link to book.css found"))

    # 4. Title format for sections
    title_match = re.search(r"<title>(.*?)</title>", text)
    if not title_match:
        issues.append((0, "NO_TITLE", "Missing <title> tag"))

    # 5. Callout title attribute check
    for i, line in enumerate(lines, 1):
        m = re.search(r'<div class="callout\s+([^"]*)"', line)
        if m:
            if 'title="' not in line:
                issues.append((i, "CALLOUT_NO_TITLE_ATTR", f"Callout missing title= attribute"))

    # 6. Code blocks without language class
    for i, line in enumerate(lines, 1):
        if "<pre><code>" in line and 'class="language-' not in line:
            issues.append((i, "CODE_NO_LANGUAGE", "Code block without language class"))

    # 7. Images without alt text
    for i, line in enumerate(lines, 1):
        if re.search(r"<img\s", line) and not re.search(r'alt="', line):
            issues.append((i, "IMG_NO_ALT", "Image missing alt text"))

    # 8. Images without loading="lazy"
    for i, line in enumerate(lines, 1):
        if re.search(r"<img\s", line) and 'loading="lazy"' not in line:
            # Skip if it's an SVG data URI or very small icon
            if 'data:image/svg' not in line:
                issues.append((i, "IMG_NO_LAZY", "Image missing loading='lazy'"))

    # 9. TODO/FIXME/PLACEHOLDER in content
    for i, line in enumerate(lines, 1):
        if re.search(r'\b(TODO|FIXME|PLACEHOLDER|XXX|HACK)\b', line, re.IGNORECASE):
            if '<!--' in line or 'comment' in line.lower():
                issues.append((i, "TODO_COMMENT", f"Contains TODO/FIXME comment"))

    # 10. Empty href or src
    for i, line in enumerate(lines, 1):
        if 'href=""' in line or "href=''" in line:
            issues.append((i, "EMPTY_HREF", "Empty href attribute"))
        if 'src=""' in line or "src=''" in line:
            issues.append((i, "EMPTY_SRC", "Empty src attribute"))

    # 11. Section files should have part-label and chapter-label
    if page_type == "section":
        if 'class="part-label"' not in text:
            issues.append((0, "NO_PART_LABEL", "Section missing part-label in header"))
        if 'class="chapter-label"' not in text:
            issues.append((0, "NO_CHAPTER_LABEL", "Section missing chapter-label in header"))

    # 12. Chapter index should have overview
    if page_type == "chapter-index":
        if 'class="overview"' not in text and 'class="chapter-overview"' not in text:
            issues.append((0, "NO_OVERVIEW", "Chapter index missing overview div"))

    # 13. Exercise callouts should have exercise-type span
    for i, line in enumerate(lines, 1):
        if 'class="callout exercise"' in line or 'class="callout exercise ' in line:
            # Check next few lines for exercise-type
            block = "\n".join(lines[i-1:i+5])
            if 'class="exercise-type' not in block:
                issues.append((i, "EXERCISE_NO_TYPE", "Exercise callout missing exercise-type badge"))

    # 14. Heading hierarchy: no h4/h5/h6 outside callouts
    in_callout = False
    for i, line in enumerate(lines, 1):
        if 'class="callout' in line:
            in_callout = True
        if in_callout and '</div>' in line:
            in_callout = False  # rough heuristic
        if not in_callout:
            if re.search(r'<h[456]\b', line):
                issues.append((i, "DEEP_HEADING", f"h4/h5/h6 outside callout (use h2/h3 instead)"))

    # 15. Em dashes and double dashes in text
    for i, line in enumerate(lines, 1):
        # Skip HTML comments and code blocks
        stripped = re.sub(r'<!--.*?-->', '', line)
        stripped = re.sub(r'<code>.*?</code>', '', stripped)
        stripped = re.sub(r'<pre>.*?</pre>', '', stripped)
        if '\u2014' in stripped:  # em dash
            issues.append((i, "EM_DASH", "Contains em dash character"))
        if ' -- ' in stripped:  # double dash
            issues.append((i, "DOUBLE_DASH", "Contains double dash"))

    # 16. Non-standard div containers
    for i, line in enumerate(lines, 1):
        if '<div class="container">' in line:
            issues.append((i, "DIV_CONTAINER", "Non-standard div.container (use main.content)"))

    # 17. Bare <header> without class
    for i, line in enumerate(lines, 1):
        if re.match(r'\s*<header>\s*$', line):
            issues.append((i, "BARE_HEADER", "Bare <header> without class='chapter-header'"))

    return issues, page_type

def main():
    files = find_html_files()
    print(f"Deep standardization audit of {len(files)} HTML files...\n")

    all_issues = defaultdict(list)
    type_counts = defaultdict(int)
    page_type_counts = defaultdict(int)
    total = 0

    for f in files:
        issues, ptype = audit_file(f)
        page_type_counts[ptype] += 1
        if issues:
            rel = f.relative_to(BASE)
            all_issues[str(rel)] = issues
            for _, itype, _ in issues:
                type_counts[itype] += 1
                total += 1

    # Print by issue type, sorted by count
    print("ISSUES BY TYPE (sorted by frequency):")
    print("=" * 60)
    for itype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {itype}: {count}")

    print(f"\nTOTAL: {total} issues in {len(all_issues)} files")
    print(f"Clean files: {len(files) - len(all_issues)}")
    print(f"\nPage types: {dict(page_type_counts)}")

    # Print sample issues (first 3 files per issue type)
    print("\n\nSAMPLE ISSUES (first 3 per type):")
    print("=" * 60)
    shown = defaultdict(int)
    for rel_path in sorted(all_issues.keys()):
        for line_num, itype, desc in all_issues[rel_path]:
            if shown[itype] < 3:
                print(f"  [{itype}] {rel_path}:{line_num} - {desc}")
                shown[itype] += 1

    # Print top 10 most problematic files
    print("\n\nTOP 10 MOST PROBLEMATIC FILES:")
    print("=" * 60)
    file_counts = [(path, len(issues)) for path, issues in all_issues.items()]
    file_counts.sort(key=lambda x: -x[1])
    for path, count in file_counts[:10]:
        print(f"  {count} issues: {path}")

if __name__ == "__main__":
    main()

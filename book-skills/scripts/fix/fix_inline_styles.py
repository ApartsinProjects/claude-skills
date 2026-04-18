#!/usr/bin/env python3
"""Remove inline styles from links, headings, divs with CSS classes,
figure tags, and img tags inside illustration figures across all HTML files."""

import os
import re
import glob

BASE_DIR = r"E:\Projects\LLMCourse"

# Directories to scan (relative to BASE_DIR)
SCAN_DIRS = ["part-*", "appendices", "front-matter"]

# Directories to exclude
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts"}

# Also process root-level HTML files (index.html, team.html, etc.)
ROOT_HTML = True


def collect_html_files():
    """Collect all .html files from target directories."""
    files = []
    # Root-level HTML
    if ROOT_HTML:
        for f in glob.glob(os.path.join(BASE_DIR, "*.html")):
            files.append(f)
    # Subdirectories
    for pattern in SCAN_DIRS:
        for dirpath in glob.glob(os.path.join(BASE_DIR, pattern)):
            for root, dirs, fnames in os.walk(dirpath):
                # Prune excluded dirs
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for fname in fnames:
                    if fname.endswith(".html"):
                        files.append(os.path.join(root, fname))
    return sorted(set(files))


# Regex: style attribute (with optional surrounding whitespace before it)
STYLE_ATTR = r'\s+style="[^"]*"'

# ---- Issue 1: <a> tags with inline style ----
# Match <a with style attribute anywhere in the opening tag
RE_A_STYLE = re.compile(r'(<a\b[^>]*?)\s+style="[^"]*"([^>]*>)', re.IGNORECASE)

# ---- Issue 2: <h2> and <h3> tags with inline style ----
RE_H_STYLE = re.compile(r'(<h[23]\b[^>]*?)\s+style="[^"]*"([^>]*>)', re.IGNORECASE)

# ---- Issue 3: <div> with known CSS class and inline style ----
KNOWN_DIV_CLASSES = {"whats-next", "overview", "figure", "illustration", "prereqs"}
RE_DIV_STYLE = re.compile(r'(<div\b[^>]*?)\s+style="[^"]*"([^>]*>)', re.IGNORECASE)

# ---- <figure> tags with inline style ----
RE_FIGURE_STYLE = re.compile(r'(<figure\b[^>]*?)\s+style="[^"]*"([^>]*>)', re.IGNORECASE)

# ---- <img> tags with inline style (inside illustration figures, but we strip all img inline styles) ----
RE_IMG_STYLE = re.compile(r'(<img\b[^>]*?)\s+style="[^"]*"([^>]*>)', re.IGNORECASE)


def has_known_class(tag_text, known_classes):
    """Check if an HTML tag contains a class attribute with one of the known classes."""
    m = re.search(r'class="([^"]*)"', tag_text, re.IGNORECASE)
    if not m:
        return False
    classes = set(m.group(1).split())
    return bool(classes & known_classes)


def fix_file(filepath):
    """Process one HTML file. Returns dict of fix counts per category."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    counts = {"a_tags": 0, "headings": 0, "divs": 0, "figures": 0, "imgs": 0}

    # 1. Fix <a> tags
    def replace_a(m):
        counts["a_tags"] += 1
        return m.group(1) + m.group(2)
    content = RE_A_STYLE.sub(replace_a, content)

    # 2. Fix <h2>/<h3> tags
    def replace_h(m):
        counts["headings"] += 1
        return m.group(1) + m.group(2)
    content = RE_H_STYLE.sub(replace_h, content)

    # 3. Fix <div> tags with known classes
    def replace_div(m):
        full_tag = m.group(0)
        if has_known_class(full_tag, KNOWN_DIV_CLASSES):
            counts["divs"] += 1
            return m.group(1) + m.group(2)
        return full_tag  # leave unchanged
    content = RE_DIV_STYLE.sub(replace_div, content)

    # 4. Fix <figure> tags
    def replace_figure(m):
        counts["figures"] += 1
        return m.group(1) + m.group(2)
    content = RE_FIGURE_STYLE.sub(replace_figure, content)

    # 5. Fix <img> tags
    def replace_img(m):
        counts["imgs"] += 1
        return m.group(1) + m.group(2)
    content = RE_IMG_STYLE.sub(replace_img, content)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return counts


def main():
    files = collect_html_files()
    print(f"Scanning {len(files)} HTML files...\n")

    totals = {"a_tags": 0, "headings": 0, "divs": 0, "figures": 0, "imgs": 0}
    files_modified = 0

    for filepath in files:
        counts = fix_file(filepath)
        total_in_file = sum(counts.values())
        if total_in_file > 0:
            files_modified += 1
            rel = os.path.relpath(filepath, BASE_DIR)
            parts = []
            if counts["a_tags"]:
                parts.append(f"{counts['a_tags']} link(s)")
            if counts["headings"]:
                parts.append(f"{counts['headings']} heading(s)")
            if counts["divs"]:
                parts.append(f"{counts['divs']} div(s)")
            if counts["figures"]:
                parts.append(f"{counts['figures']} figure(s)")
            if counts["imgs"]:
                parts.append(f"{counts['imgs']} img(s)")
            print(f"  {rel}: {', '.join(parts)}")
            for k in totals:
                totals[k] += counts[k]

    print(f"\nSummary")
    print(f"  Files scanned:  {len(files)}")
    print(f"  Files modified: {files_modified}")
    print(f"  Links fixed:    {totals['a_tags']}")
    print(f"  Headings fixed: {totals['headings']}")
    print(f"  Divs fixed:     {totals['divs']}")
    print(f"  Figures fixed:  {totals['figures']}")
    print(f"  Imgs fixed:     {totals['imgs']}")
    print(f"  Total fixes:    {sum(totals.values())}")


if __name__ == "__main__":
    main()

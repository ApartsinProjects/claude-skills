#!/usr/bin/env python3
"""
fix_callout_icons.py
Removes leftover HTML entity emoji prefixes from callout-title divs.

The CSS system (book.css) already provides icons for all callout types via
::before pseudo-elements. Some callout-title divs still contain HTML entity
emoji prefixes (e.g. &#9733; &#x1F3D7;&#xFE0F;) causing double icons.

This script strips those entity prefixes and normalizes "Application Example"
to "Practical Example".
"""

import os
import re
import glob

BASE_DIR = r"E:\Projects\LLMCourse"

# Directories to scan
SCAN_DIRS = [
    "part-1-foundations",
    "part-2-understanding-llms",
    "part-3-working-with-llms",
    "part-4-training-adapting",
    "part-5-retrieval-conversation",
    "part-6-agents-applications",
    "part-7-production-strategy",
    "appendices",
    "front-matter",
    "capstone",
]

# Directories to exclude
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts"}

# Pattern to match callout-title with HTML entity prefix
# Captures: (before)(entity_prefix + optional whitespace)(title_text)(after)
CALLOUT_TITLE_RE = re.compile(
    r'(<div\s+class="callout-title">)'   # group 1: opening tag
    r'((?:&#x?[0-9a-fA-F]+;\s*)+)'       # group 2: one or more HTML entities + whitespace
    r'(.*?)'                               # group 3: title text
    r'(</div>)',                           # group 4: closing tag
    re.IGNORECASE
)

# Pattern for raw Unicode emoji characters (U+1F000 and above, plus some symbols)
UNICODE_EMOJI_RE = re.compile(
    r'(<div\s+class="callout-title">)'
    r'([\U0001F000-\U0001FFFF\u2600-\u27BF\u2B50\u2728\u26A0\u2699\u2733\u26A1\u2764\uFE0F]+\s*)'
    r'(.*?)'
    r'(</div>)',
    re.IGNORECASE
)

# Title normalization map
TITLE_NORMALIZATIONS = {
    "Application Example": "Practical Example",
}


def collect_html_files():
    """Collect all .html files from the scan directories."""
    files = []
    for scan_dir in SCAN_DIRS:
        full_path = os.path.join(BASE_DIR, scan_dir)
        if not os.path.isdir(full_path):
            continue
        for root, dirs, filenames in os.walk(full_path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in filenames:
                if fname.endswith(".html"):
                    files.append(os.path.join(root, fname))
    return sorted(files)


def fix_callout_title(match):
    """Replace callback: remove entity prefix, normalize title."""
    opening_tag = match.group(1)
    title_text = match.group(3).strip()
    closing_tag = match.group(4)

    # Apply title normalizations
    for old_title, new_title in TITLE_NORMALIZATIONS.items():
        if title_text == old_title:
            title_text = new_title
            break

    return f"{opening_tag}{title_text}{closing_tag}"


def fix_unicode_emoji_title(match):
    """Replace callback for raw Unicode emoji prefix."""
    opening_tag = match.group(1)
    title_text = match.group(3).strip()
    closing_tag = match.group(4)

    for old_title, new_title in TITLE_NORMALIZATIONS.items():
        if title_text == old_title:
            title_text = new_title
            break

    return f"{opening_tag}{title_text}{closing_tag}"


def process_file(filepath):
    """Process a single HTML file and return list of changes."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    changes = []

    # Find all matches before replacing (for reporting)
    for m in CALLOUT_TITLE_RE.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        before = m.group(0)
        after = fix_callout_title(m)
        if before != after:
            changes.append((line_num, before, after))

    # Apply HTML entity fixes
    content = CALLOUT_TITLE_RE.sub(fix_callout_title, content)

    # Check for raw Unicode emoji (second pass)
    for m in UNICODE_EMOJI_RE.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        before = m.group(0)
        after = fix_unicode_emoji_title(m)
        if before != after:
            changes.append((line_num, before, after))

    content = UNICODE_EMOJI_RE.sub(fix_unicode_emoji_title, content)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return changes


def main():
    html_files = collect_html_files()
    print(f"Scanning {len(html_files)} HTML files...\n")

    total_fixes = 0
    files_changed = 0

    for filepath in html_files:
        changes = process_file(filepath)
        if changes:
            files_changed += 1
            rel_path = os.path.relpath(filepath, BASE_DIR)
            for line_num, before, after in changes:
                total_fixes += 1
                # Truncate long lines for display
                before_short = before if len(before) < 120 else before[:117] + "..."
                after_short = after if len(after) < 120 else after[:117] + "..."
                print(f"  {rel_path}:{line_num}")
                print(f"    BEFORE: {before_short}")
                print(f"    AFTER:  {after_short}")
                print()

    print("=" * 70)
    print(f"Summary: {total_fixes} fixes across {files_changed} files")
    print(f"Total HTML files scanned: {len(html_files)}")


if __name__ == "__main__":
    main()

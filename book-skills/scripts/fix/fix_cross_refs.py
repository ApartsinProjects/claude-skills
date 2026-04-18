#!/usr/bin/env python3
"""
fix_cross_refs.py
Add class="cross-ref" to cross-reference links in all HTML files.

A cross-reference link is an <a> tag whose href:
  - contains ../ (goes up at least one directory level)
  - contains 'module-' or 'part-' or 'appendix-' in the path
  - does NOT already have a class= attribute
  - is NOT inside an exclusion zone (nav, chapter-nav, chapter-card,
    sections-list, section-list, bibliography blocks)
  - is NOT an external link (http:// or https://)
  - is NOT an anchor-only link (#...)
"""

import os
import re
import sys

BASE_DIR = r"E:\Projects\LLMCourse"

# Regex to match <a ...> tags (non-greedy, single tags only)
A_TAG_RE = re.compile(r'<a\b([^>]*)>', re.IGNORECASE)

# Regex to extract href value
HREF_RE = re.compile(r'''href\s*=\s*["']([^"']+)["']''', re.IGNORECASE)

# Regex to detect existing class attribute
CLASS_RE = re.compile(r'''class\s*=\s*["']''', re.IGNORECASE)

# Exclusion zone opening tags (we track nesting simply by looking backward)
EXCLUSION_OPENERS = [
    '<nav class="header-nav"',
    '<nav class="chapter-nav"',
    '<div class="chapter-card"',
    '<ul class="sections-list"',
    '<ul class="section-list"',
    '<div class="bibliography',
]

# Corresponding close tags
EXCLUSION_CLOSERS = {
    '<nav class="header-nav"': '</nav>',
    '<nav class="chapter-nav"': '</nav>',
    '<div class="chapter-card"': '</div>',
    '<ul class="sections-list"': '</ul>',
    '<ul class="section-list"': '</ul>',
    '<div class="bibliography': '</div>',
}


def is_cross_ref_href(href):
    """Check if an href qualifies as a cross-reference."""
    # Must go up at least one directory
    if '../' not in href:
        return False
    # Must not be external
    if href.startswith('http://') or href.startswith('https://'):
        return False
    # Must not be anchor-only
    if href.startswith('#'):
        return False
    # Must reference another module, part, or appendix
    if 'module-' not in href and 'part-' not in href and 'appendix-' not in href:
        return False
    return True


def in_exclusion_zone(content, pos):
    """
    Check if position `pos` in `content` is inside an exclusion zone.

    Strategy: look backward from pos (up to 3000 chars) for exclusion zone
    openers. If we find one, check whether its corresponding closer appears
    between the opener and pos. If no closer found, we are inside the zone.
    """
    lookback = max(0, pos - 3000)
    preceding = content[lookback:pos]

    for opener in EXCLUSION_OPENERS:
        # Find the LAST occurrence of this opener before pos
        idx = preceding.rfind(opener)
        if idx == -1:
            continue
        # absolute position of opener in content
        abs_opener = lookback + idx
        # Look for the corresponding closer between opener and pos
        closer = EXCLUSION_CLOSERS[opener]
        # Search from after the opener tag to pos
        # First, find end of the opener tag
        tag_end = content.find('>', abs_opener)
        if tag_end == -1:
            continue
        search_region = content[tag_end + 1:pos]

        # For nav and ul, we need to find the matching close tag.
        # Simple approach: count nesting for the tag type.
        if opener.startswith('<nav'):
            # Count <nav opens vs </nav> closes
            opens = len(re.findall(r'<nav\b', search_region, re.IGNORECASE))
            closes = len(re.findall(r'</nav>', search_region, re.IGNORECASE))
            # The opener itself is already counted (it is before search_region)
            # so we need closes > opens for the zone to be closed
            if closes <= opens:
                return True
        elif opener.startswith('<ul'):
            opens = len(re.findall(r'<ul\b', search_region, re.IGNORECASE))
            closes = len(re.findall(r'</ul>', search_region, re.IGNORECASE))
            if closes <= opens:
                return True
        elif opener.startswith('<div'):
            opens = len(re.findall(r'<div\b', search_region, re.IGNORECASE))
            closes = len(re.findall(r'</div>', search_region, re.IGNORECASE))
            if closes <= opens:
                return True

    return False


def process_file(filepath):
    """Process a single HTML file. Returns number of links modified."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    modified_count = 0
    new_content = []
    last_end = 0

    for match in A_TAG_RE.finditer(content):
        attrs = match.group(1)
        tag_start = match.start()

        # Check if already has a class attribute
        if CLASS_RE.search(attrs):
            continue

        # Extract href
        href_match = HREF_RE.search(attrs)
        if not href_match:
            continue
        href = href_match.group(1)

        # Check if this is a cross-reference href
        if not is_cross_ref_href(href):
            continue

        # Check exclusion zones
        if in_exclusion_zone(content, tag_start):
            continue

        # This link qualifies. Add class="cross-ref" right after <a
        new_content.append(content[last_end:match.start()])
        new_tag = '<a class="cross-ref" ' + attrs.strip() + '>'
        new_content.append(new_tag)
        last_end = match.end()
        modified_count += 1

    if modified_count > 0:
        new_content.append(content[last_end:])
        result = ''.join(new_content)
        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(result)

    return modified_count


def find_html_files(base_dir):
    """Find all HTML files in the project."""
    html_files = []
    for root, dirs, files in os.walk(base_dir):
        # Skip hidden directories and common non-content dirs
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '_lab_fragments', 'scripts')]
        for fname in files:
            if fname.endswith('.html'):
                html_files.append(os.path.join(root, fname))
    return html_files


def main():
    html_files = find_html_files(BASE_DIR)
    html_files.sort()

    total_modified_links = 0
    files_modified = 0

    print(f"Scanning {len(html_files)} HTML files...")
    print()

    for filepath in html_files:
        count = process_file(filepath)
        if count > 0:
            rel_path = os.path.relpath(filepath, BASE_DIR)
            print(f"  {rel_path}: {count} links updated")
            total_modified_links += count
            files_modified += 1

    print()
    print(f"Summary: {total_modified_links} cross-reference links updated across {files_modified} files.")


if __name__ == '__main__':
    main()

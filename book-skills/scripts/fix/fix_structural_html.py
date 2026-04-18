#!/usr/bin/env python3
"""Fix 4 systematic structural issues across all HTML section pages.

Issues fixed:
1. Epigraph outside .content wrapper (move inside)
2. Broken callout class quotes: class="callout "tip" -> class="callout tip"
3. Nav with inline styles -> <nav class="chapter-nav"> with link classes
4. Trailing elements outside .content (bibliography, research-frontier, etc.)
"""

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories to skip
SKIP_DIRS = {'agents', 'templates', '_scripts_archive', 'vendor', 'styles',
             '.claude', '.git', 'node_modules', '_lab_fragments'}

counters = {
    'epigraph_moved': 0,
    'callout_quotes_fixed': 0,
    'nav_inline_fixed': 0,
    'content_wrapper_fixed': 0,
    'files_modified': 0,
}


def should_process(filepath):
    """Only process section HTML files in part-* and appendices dirs."""
    rel = os.path.relpath(filepath, ROOT).replace('\\', '/')
    parts = rel.split('/')
    if any(d in SKIP_DIRS for d in parts):
        return False
    # Process section files and index files in module/appendix dirs
    if not filepath.endswith('.html'):
        return False
    return True


def fix_epigraph_outside_content(text):
    """Issue 1: Move epigraph from before content div to just inside it."""
    count = 0

    # Pattern: </header>\n<blockquote class="epigraph">...</blockquote>\n<div/main class="content">
    # We need to capture the epigraph block and swap it with the content opener
    pattern = re.compile(
        r'(</header>\s*\n)'                          # group 1: closing header
        r'(\s*<blockquote class="epigraph">.*?</blockquote>\s*\n)'  # group 2: epigraph block
        r'(\s*<(?:div|main) class="content">)',       # group 3: content opener
        re.DOTALL
    )

    def replacer(m):
        nonlocal count
        count += 1
        header_close = m.group(1)
        epigraph = m.group(2).strip()
        content_open = m.group(3).strip()
        return f"{header_close}\n{content_open}\n\n    {epigraph}\n"

    text = pattern.sub(replacer, text)
    return text, count


def fix_callout_broken_quotes(text):
    """Issue 2: Fix class="callout "tip" -> class="callout tip" etc."""
    count = 0

    def replacer(m):
        nonlocal count
        count += 1
        callout_type = m.group(1)
        return f'class="callout {callout_type}"'

    # Pattern: class="callout "word"  (the first quote closes early, then word has a trailing quote)
    text, n = re.subn(r'class="callout "(\w+)"', replacer, text)
    return text, count


def fix_nav_inline_styles(text):
    """Issue 3: Replace inline-styled nav with class-based nav."""
    count = 0

    # Match the entire nav block with inline styles
    # Two known variants of inline style
    nav_pattern = re.compile(
        r'<nav\s+style="display:flex;[^"]*">\s*\n'
        r'(.*?)'
        r'</nav>',
        re.DOTALL
    )

    def replacer(m):
        nonlocal count
        count += 1
        inner = m.group(1)
        # Parse out the links
        links = re.findall(r'<a[^>]*>.*?</a>', inner, re.DOTALL)
        new_links = []
        for link in links:
            # Determine type based on content
            if '&larr;' in link or '&laquo;' in link or 'Prev' in link or 'Previous' in link:
                # Add class="prev" if not already present
                if 'class="prev"' not in link:
                    link = re.sub(r'<a\s', '<a class="prev" ', link)
                    # Remove other class attrs if we doubled up
                    link = re.sub(r'class="prev"\s+class="[^"]*"', 'class="prev"', link)
                # Normalize: keep existing href, standardize the link
                new_links.append(link.strip())
            elif 'Up:' in link or '&#x2191;' in link or 'Chapter' in link and '&rarr;' not in link and '&raquo;' not in link and '&larr;' not in link and '&laquo;' not in link:
                if 'class="up"' not in link:
                    link = re.sub(r'<a\s', '<a class="up" ', link)
                    link = re.sub(r'class="up"\s+class="[^"]*"', 'class="up"', link)
                new_links.append(link.strip())
            elif '&rarr;' in link or '&raquo;' in link or 'Next' in link:
                if 'class="next"' not in link:
                    link = re.sub(r'<a\s', '<a class="next" ', link)
                    link = re.sub(r'class="next"\s+class="[^"]*"', 'class="next"', link)
                new_links.append(link.strip())
            else:
                # Middle link (likely "Up" link without explicit marker)
                if 'class=' not in link:
                    link = re.sub(r'<a\s', '<a class="up" ', link)
                new_links.append(link.strip())

        result = '<nav class="chapter-nav">\n'
        for lnk in new_links:
            result += f'    {lnk}\n'
        result += '</nav>'
        return result

    text = nav_pattern.sub(replacer, text)
    return text, count


def fix_content_wrapper_closing(text):
    """Issue 4: Ensure closing tag for .content wraps trailing elements.

    Trailing elements that should be inside .content:
    - <section class="bibliography">
    - <div class="callout research-frontier"
    - <div class="whats-next">
    - <div class="quiz">
    - <div class="takeaways">
    - <nav class="chapter-nav">

    Strategy: Find the </main> or </div> that closes .content. If any trailing
    markers appear AFTER that close tag but before </body>, remove the premature
    close tag and re-insert it just before </body>.
    """
    # Find the content opening tag
    content_open_match = re.search(r'<(main|div)\s+class="content">', text)
    if not content_open_match:
        return text, 0

    content_tag = content_open_match.group(1)  # 'main' or 'div'
    content_start = content_open_match.end()
    close_tag = f'</{content_tag}>'

    body_end = text.find('</body>')
    if body_end == -1:
        return text, 0

    # Elements that should be inside .content
    trailing_markers = [
        '<section class="bibliography">',
        '<div class="callout research-frontier"',
        '<div class="whats-next">',
        '<div class="quiz">',
        '<div class="takeaways">',
        '<nav class="chapter-nav">',
    ]

    # Find ALL occurrences of close_tag between content_start and body_end
    # The .content closer should be the one closest to </body>
    # (since inner divs/mains would have their own closers earlier)
    close_positions = []
    search_pos = content_start
    while True:
        pos = text.find(close_tag, search_pos, body_end)
        if pos == -1:
            break
        close_positions.append(pos)
        search_pos = pos + len(close_tag)

    if not close_positions:
        return text, 0

    # The last close_tag before </body> is most likely the .content closer
    content_close_pos = close_positions[-1]

    # Check if any trailing markers appear AFTER this close tag
    trailing_after_close = False
    for marker in trailing_markers:
        pos = text.find(marker, content_close_pos)
        if pos != -1 and pos < body_end:
            trailing_after_close = True
            break

    if not trailing_after_close:
        # Everything is already inside .content, no fix needed
        return text, 0

    # We need to move the close tag to just before </body>
    # Remove the premature close tag
    line_start = text.rfind('\n', 0, content_close_pos)
    line_end = text.find('\n', content_close_pos)
    if line_end == -1:
        line_end = content_close_pos + len(close_tag)

    # Check that the line containing close_tag is just the tag (possibly with whitespace)
    line_content = text[line_start+1:line_end].strip()
    if line_content != close_tag:
        # The close tag shares a line with other content; be conservative
        text_before = text[:content_close_pos]
        text_after = text[content_close_pos + len(close_tag):]
        text = text_before + text_after
    else:
        # Remove the entire line
        text = text[:line_start+1] + text[line_end+1:]

    # Re-find </body> since positions shifted
    body_end = text.find('</body>')
    if body_end == -1:
        return text, 0

    # Insert close_tag just before </body>
    # Find the right spot: after the last trailing element, before </body>
    insert_pos = body_end
    # Back up past any whitespace
    while insert_pos > 0 and text[insert_pos-1] in ' \t\n\r':
        insert_pos -= 1

    text = text[:insert_pos] + f'\n{close_tag}\n\n' + text[insert_pos:]

    return text, 1


def process_file(filepath):
    """Apply all fixes to a single file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()

    text = original

    text, c1 = fix_epigraph_outside_content(text)
    counters['epigraph_moved'] += c1

    text, c2 = fix_callout_broken_quotes(text)
    counters['callout_quotes_fixed'] += c2

    text, c3 = fix_nav_inline_styles(text)
    counters['nav_inline_fixed'] += c3

    text, c4 = fix_content_wrapper_closing(text)
    counters['content_wrapper_fixed'] += c4

    if text != original:
        counters['files_modified'] += 1
        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        return True
    return False


def main():
    # Glob all HTML files
    patterns = [
        os.path.join(ROOT, 'part-*', '**', '*.html'),
        os.path.join(ROOT, 'appendices', '**', '*.html'),
        os.path.join(ROOT, 'front-matter', '**', '*.html'),
        os.path.join(ROOT, 'capstone', '**', '*.html'),
    ]

    all_files = set()
    for pat in patterns:
        all_files.update(glob.glob(pat, recursive=True))

    # Filter
    files = sorted(f for f in all_files if should_process(f))
    print(f"Processing {len(files)} HTML files...")

    modified_files = []
    for filepath in files:
        if process_file(filepath):
            modified_files.append(os.path.relpath(filepath, ROOT))

    print(f"\nResults:")
    print(f"  Epigraphs moved inside .content: {counters['epigraph_moved']}")
    print(f"  Broken callout quotes fixed:     {counters['callout_quotes_fixed']}")
    print(f"  Inline nav styles replaced:      {counters['nav_inline_fixed']}")
    print(f"  Content wrappers extended:        {counters['content_wrapper_fixed']}")
    print(f"  Total files modified:             {counters['files_modified']}")

    if modified_files:
        print(f"\nModified files:")
        for f in modified_files:
            print(f"  {f}")


if __name__ == '__main__':
    main()

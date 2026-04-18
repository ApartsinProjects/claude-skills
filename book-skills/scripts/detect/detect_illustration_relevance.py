"""Extract illustrations and their surrounding context for relevance auditing.

For each section-*.html file, outputs:
  - Section title
  - Each illustration's caption text
  - The nearest heading (h2/h3) above the illustration
  - SVG title/desc if present
  - Whether the caption references the section topic

This creates a structured report for reviewing illustration relevance.
"""
import re
import sys
from pathlib import Path


def extract_title(html):
    m = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        title = re.split(r'\s*[\|]', title)[0].strip()
        return title
    return "Unknown"


def find_nearest_heading(lines, target_line):
    """Find the nearest h2/h3 heading above the target line."""
    for i in range(target_line - 1, -1, -1):
        m = re.search(r'<h([23])[^>]*>(.*?)</h\1>', lines[i], re.DOTALL)
        if m:
            return re.sub(r'<[^>]+>', '', m.group(2)).strip()
    return None


def extract_illustrations(filepath, html):
    """Extract all illustrations with their captions and context."""
    lines = html.split('\n')
    illustrations = []

    for i, line in enumerate(lines):
        # Look for diagram-caption or generic caption
        caption_match = re.search(r'class="diagram-caption"[^>]*>(.*?)(?:</div>|$)', line, re.DOTALL)
        if not caption_match:
            caption_match = re.search(r'class="caption"[^>]*>(.*?)(?:</div>|$)', line, re.DOTALL)
        if not caption_match:
            continue

        caption_text = caption_match.group(1).strip()
        # If caption spans multiple lines, grab them
        if '</div>' not in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                caption_text += ' ' + lines[j].strip()
                if '</div>' in lines[j]:
                    break

        caption_text = re.sub(r'<[^>]+>', '', caption_text).strip()
        if len(caption_text) > 200:
            caption_text = caption_text[:197] + '...'

        heading = find_nearest_heading(lines, i)

        # Check for SVG title nearby (within 30 lines above)
        svg_title = None
        for j in range(max(0, i - 30), i):
            tm = re.search(r'<title>(.*?)</title>', lines[j])
            if tm and '<head>' not in lines[max(0, j-5):j+1]:
                svg_title = tm.group(1).strip()

        # Check for img alt text nearby
        img_alt = None
        for j in range(max(0, i - 10), i + 3):
            am = re.search(r'alt="([^"]*)"', lines[j])
            if am:
                img_alt = am.group(1).strip()

        illustrations.append({
            'line': i + 1,
            'caption': caption_text,
            'heading': heading,
            'svg_title': svg_title,
            'img_alt': img_alt,
        })

    return illustrations


def main():
    book_root = Path('.')
    section_files = sorted(book_root.glob('part-*/module-*/section-*.html'))
    section_files += sorted(book_root.glob('appendices/appendix-*/section-*.html'))

    total_illustrations = 0
    files_with_illustrations = 0

    for f in section_files:
        html = f.read_text(encoding='utf-8', errors='replace')
        title = extract_title(html)
        illustrations = extract_illustrations(f, html)

        if not illustrations:
            continue

        files_with_illustrations += 1
        total_illustrations += len(illustrations)

        print(f"\n{'='*80}")
        print(f"FILE: {f}")
        print(f"TITLE: {title}")
        print(f"ILLUSTRATIONS ({len(illustrations)}):")
        for idx, ill in enumerate(illustrations, 1):
            print(f"  [{idx}] Line {ill['line']}: {ill['caption']}")
            if ill['heading']:
                print(f"       Under heading: {ill['heading']}")
            if ill['svg_title']:
                print(f"       SVG title: {ill['svg_title']}")
            if ill['img_alt']:
                print(f"       Image alt: {ill['img_alt']}")

    print(f"\n{'='*80}")
    print(f"SUMMARY: {total_illustrations} illustrations in {files_with_illustrations} files")


if __name__ == '__main__':
    main()

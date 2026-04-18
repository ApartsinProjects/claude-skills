"""Extract section topics and bibliography entries for relevance auditing.

For each section-*.html file that has a bibliography, outputs:
  - Section title (from <title> or <h1>)
  - Section headings (h2/h3) to understand scope
  - Each bib entry's citation text (first 120 chars)

This creates a structured report that a reviewer (human or LLM) can scan
to identify references that don't belong in a given section.
"""
import re
import sys
from pathlib import Path
from collections import defaultdict


def extract_title(html):
    """Extract section title from <title> tag."""
    m = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # Remove book title suffix
        title = re.split(r'\s*[\|–]\s*', title)[0].strip()
        return title
    return "Unknown"


def extract_headings(html):
    """Extract h2 and h3 headings to understand section scope."""
    headings = []
    for m in re.finditer(r'<h([23])[^>]*>(.*?)</h\1>', html, re.DOTALL):
        level = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        # Skip structural headings
        if text in ('What\'s Next?', 'References & Further Reading', 'Prerequisites'):
            continue
        if len(text) > 80:
            text = text[:77] + '...'
        headings.append(f"  h{level}: {text}")
    return headings


def extract_bib_entries(html):
    """Extract bibliography reference texts."""
    entries = []
    # Find bib-ref paragraphs
    for m in re.finditer(r'<p class="bib-ref">(.*?)</p>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(text) > 150:
            text = text[:147] + '...'
        entries.append(text)

    # Also check for old-style <li> entries inside bibliography
    bib_match = re.search(r'class="bibliography".*?</(?:section|div)>', html, re.DOTALL)
    if bib_match and not entries:
        for m in re.finditer(r'<li[^>]*>(.*?)</li>', bib_match.group(), re.DOTALL):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if len(text) > 150:
                text = text[:147] + '...'
            entries.append(text)

    return entries


def extract_bib_categories(html):
    """Extract bibliography category headings."""
    cats = []
    for m in re.finditer(r'<div class="bib-category">(.*?)</div>', html, re.DOTALL):
        cats.append(re.sub(r'<[^>]+>', '', m.group(1)).strip())
    return cats


def main():
    book_root = Path('.')
    section_files = sorted(book_root.glob('part-*/module-*/section-*.html'))
    section_files += sorted(book_root.glob('appendices/appendix-*/section-*.html'))

    total_sections = 0
    total_refs = 0
    sections_without_bib = 0

    for f in section_files:
        html = f.read_text(encoding='utf-8', errors='replace')

        entries = extract_bib_entries(html)
        if not entries:
            sections_without_bib += 1
            continue

        total_sections += 1
        total_refs += len(entries)

        title = extract_title(html)
        headings = extract_headings(html)
        categories = extract_bib_categories(html)

        print(f"\n{'='*80}")
        print(f"FILE: {f}")
        print(f"TITLE: {title}")
        if headings:
            print(f"SCOPE ({len(headings)} headings):")
            for h in headings[:10]:
                print(h)
            if len(headings) > 10:
                print(f"  ... and {len(headings)-10} more")
        if categories:
            print(f"BIB CATEGORIES: {', '.join(categories)}")
        print(f"REFERENCES ({len(entries)}):")
        for i, entry in enumerate(entries, 1):
            print(f"  [{i}] {entry}")

    print(f"\n{'='*80}")
    print(f"SUMMARY: {total_sections} sections with bibliographies, {total_refs} total references")
    print(f"         {sections_without_bib} sections without bibliographies")
    print(f"         Average: {total_refs/max(total_sections,1):.1f} refs per section")


if __name__ == '__main__':
    main()

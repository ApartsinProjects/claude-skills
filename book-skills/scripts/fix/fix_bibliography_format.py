"""Standardize bibliography sections across all section HTML files.

Converts non-canonical bibliography formats to the canonical card-based format:
- Replaces <h2>Bibliography</h2> or <h2>Bibliography and Further Reading</h2>
  with <div class="bibliography-title">References &amp; Further Reading</div>
- Converts <ul><li> list items to <div class="bib-entry-card"> cards
- Adds bib-annotation from bib-note spans if present
- Infers bib-meta type from content (Paper, Book, Tool, etc.)
- Groups entries under a "Key References" category if no categories exist

Only processes section-*.html files (not index.html, not chapter/part indexes).
"""
import re
import os
import sys
from pathlib import Path


def infer_type(text):
    """Infer bibliography entry type from text content."""
    lower = text.lower()
    if any(w in lower for w in ['arxiv', 'proceedings', 'conference', 'journal',
                                  'neurips', 'icml', 'iclr', 'acl', 'emnlp',
                                  'aaai', 'cvpr', 'naacl', 'ieee', 'nature',
                                  'science', 'et al.']):
        return '&#128196; Paper'
    if any(w in lower for w in ['press', 'edition', 'publisher', 'book',
                                  'o\'reilly', 'springer', 'cambridge',
                                  'mit press', 'farrar', 'penguin']):
        return '&#128214; Book'
    if any(w in lower for w in ['github.com', 'docs.', 'documentation',
                                  'sdk', 'library', 'framework', 'toolkit',
                                  'platform', 'tool', '.io/', 'pypi']):
        return '&#128736; Tool'
    if any(w in lower for w in ['blog', 'post', 'medium.com', 'substack',
                                  'lilianweng', 'huggingface.co/blog']):
        return '&#128221; Blog'
    if any(w in lower for w in ['tutorial', 'guide', 'course', 'lecture']):
        return '&#127891; Tutorial'
    return '&#128196; Paper'


def extract_link(li_html):
    """Extract href and link text from a <li> element."""
    link_match = re.search(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', li_html, re.DOTALL)
    if link_match:
        return link_match.group(1), link_match.group(2)
    return None, None


def parse_li_entry(li_html):
    """Parse a <li> bibliography entry into components."""
    # Remove the <li> tags
    inner = re.sub(r'^\s*<li[^>]*>', '', li_html).strip()
    inner = re.sub(r'</li>\s*$', '', inner).strip()

    # Check for bib-note span (annotation)
    annotation = ''
    bib_note = re.search(r'<span class="bib-note">(.*?)</span>', inner, re.DOTALL)
    if bib_note:
        annotation = bib_note.group(1).strip()
        inner = inner[:bib_note.start()].strip()
        # Clean trailing period/space before the note
        inner = inner.rstrip('. ')

    # Check for existing link
    href, _ = extract_link(inner)

    # Build the ref text (the full citation)
    ref_text = inner.strip()

    # Infer type
    entry_type = infer_type(ref_text)

    return ref_text, annotation, entry_type, href


def convert_ul_bibliography(bib_html):
    """Convert a <ul><li> bibliography to card-based format."""
    # Extract all <li> entries
    li_entries = re.findall(r'<li[^>]*>.*?</li>', bib_html, re.DOTALL)

    if not li_entries:
        return bib_html  # Nothing to convert

    cards = []
    cards.append('    <div class="bib-category">Key References</div>\n')

    for li in li_entries:
        ref_text, annotation, entry_type, href = parse_li_entry(li)

        # Build card
        card = '    <div class="bib-entry-card">\n'

        if href and 'target=' not in ref_text:
            # Wrap in link if there's an href but no target attr yet
            card += f'        <p class="bib-ref">{ref_text}</p>\n'
        else:
            card += f'        <p class="bib-ref">{ref_text}</p>\n'

        if annotation:
            card += f'        <p class="bib-annotation">{annotation}</p>\n'

        card += f'        <span class="bib-meta">{entry_type}</span>\n'
        card += '    </div>\n'
        cards.append(card)

    return '\n'.join(cards)


def fix_bibliography(filepath):
    """Fix bibliography format in a single file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    original = content
    changed = False

    # Pattern 1: <h2>Bibliography</h2> inside a div/section.bibliography
    # Replace heading with bibliography-title div
    heading_patterns = [
        (r'<h2>\s*Bibliography\s*</h2>', '<div class="bibliography-title">References &amp; Further Reading</div>'),
        (r'<h2>\s*Bibliography and Further Reading\s*</h2>', '<div class="bibliography-title">References &amp; Further Reading</div>'),
        (r'<h2>\s*References\s*</h2>', '<div class="bibliography-title">References &amp; Further Reading</div>'),
        (r'<h2>\s*References and Further Reading\s*</h2>', '<div class="bibliography-title">References &amp; Further Reading</div>'),
        (r'<h2>\s*Annotated Bibliography\s*</h2>', '<div class="bibliography-title">References &amp; Further Reading</div>'),
        (r'<h2>\s*Further Reading\s*</h2>', '<div class="bibliography-title">References &amp; Further Reading</div>'),
    ]

    for pattern, replacement in heading_patterns:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            changed = True

    # Also fix <h3> category headings that should be bib-category divs
    # But only inside bibliography sections

    # Convert <section class="bibliography"> to <div class="bibliography">
    if '<section class="bibliography">' in content:
        content = content.replace('<section class="bibliography">', '<div class="bibliography">')
        content = content.replace('</section>', '</div>', 1)  # Only first occurrence after bibliography
        changed = True

    # Find and convert <ul><li> blocks inside bibliography divs
    bib_match = re.search(
        r'(<div class="bibliography">.*?<div class="bibliography-title">.*?</div>)\s*\n\s*(<ul>.*?</ul>)',
        content, re.DOTALL
    )

    if bib_match:
        ul_block = bib_match.group(2)
        card_block = convert_ul_bibliography(ul_block)
        content = content[:bib_match.start(2)] + card_block + content[bib_match.end(2):]
        changed = True

    # Handle case where <ul> is directly after bibliography-title without other structure
    # Also handle multiple <ul> blocks (some files have categorized lists with h3 headers)
    remaining_uls = list(re.finditer(
        r'(class="bibliography".*?)((<h3>[^<]+</h3>\s*)?<ul>.*?</ul>)',
        content, re.DOTALL
    ))

    if changed and not original == content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True

    return False


def main():
    book_root = Path(os.environ.get('BOOK_ROOT', '.'))

    section_files = sorted(book_root.glob('part-*/module-*/section-*.html'))
    section_files += sorted(book_root.glob('appendices/appendix-*/section-*.html'))

    fixed = 0
    for f in section_files:
        html = f.read_text(encoding='utf-8', errors='replace')

        # Check if this file has a non-canonical bibliography
        has_h2_bib = bool(re.search(
            r'<h2>\s*(Bibliography|References|Annotated Bibliography|Further Reading|Bibliography and Further Reading|References and Further Reading)\s*</h2>',
            html
        ))

        if has_h2_bib:
            if fix_bibliography(f):
                fixed += 1
                print(f'Fixed: {f.relative_to(book_root)}')
            else:
                print(f'Skipped (complex structure): {f.relative_to(book_root)}')

    print(f'\nFixed {fixed} files')


if __name__ == '__main__':
    main()

"""Move callouts/content that appear between whats-next and bibliography (or after whats-next
with no bibliography) to just before the whats-next div.

Also moves labs placed after bibliography to just before whats-next.

Handles two patterns:
1. <div class="callout ..."> between </div><!--whats-next--> and <section class="bibliography">
2. <div class="lab"> after <section class="bibliography"> or <div class="bibliography">
"""
import re
import sys
from pathlib import Path


def find_div_block(lines, start_idx):
    """Find the full div block starting at start_idx, tracking nesting."""
    depth = 0
    block_lines = []
    for i in range(start_idx, len(lines)):
        line = lines[i]
        block_lines.append(line)
        depth += line.count('<div')
        depth += line.count('<section')
        depth -= line.count('</div')
        depth -= line.count('</section')
        if depth <= 0 and len(block_lines) > 0:
            return i, block_lines
    return len(lines) - 1, block_lines


def fix_file(filepath):
    """Fix content ordering in a single file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')
    changed = False

    # Find whats-next position
    wn_start = None
    wn_end = None
    for i, line in enumerate(lines):
        if 'class="whats-next"' in line:
            wn_start = i
            wn_end_idx, _ = find_div_block(lines, i)
            wn_end = wn_end_idx
            break

    # Find bibliography position
    bib_start = None
    for i, line in enumerate(lines):
        if 'class="bibliography"' in line:
            bib_start = i
            break

    # If no whats-next and no bibliography, nothing to fix
    if wn_start is None and bib_start is None:
        return False

    nav_start = None
    for i, line in enumerate(lines):
        if 'class="chapter-nav"' in line:
            nav_start = i
            break

    blocks_to_move = []
    skip_to = -1

    # Collect callouts between whats-next end and bibliography
    if wn_start is not None and wn_end is not None:
        end_marker = bib_start if bib_start else (nav_start or len(lines))
        for i in range(wn_end + 1, end_marker):
            if i <= skip_to:
                continue
            line = lines[i]
            if re.search(r'<div\s+class="callout\s', line):
                block_end, block_lines = find_div_block(lines, i)
                blocks_to_move.append((i, block_end, block_lines))
                skip_to = block_end

    # Check for labs after bibliography
    if bib_start:
        bib_end_idx = bib_start
        depth = 0
        for i in range(bib_start, len(lines)):
            depth += lines[i].count('<section') + lines[i].count('<div')
            depth -= lines[i].count('</section') + lines[i].count('</div')
            if depth <= 0 and i > bib_start:
                bib_end_idx = i
                break

        scan_end = nav_start if nav_start else len(lines)
        for i in range(bib_end_idx + 1, scan_end):
            if i <= skip_to:
                continue
            line = lines[i]
            if 'class="lab"' in line or 'class="lab ' in line:
                block_end, block_lines = find_div_block(lines, i)
                blocks_to_move.append((i, block_end, block_lines))
                skip_to = block_end

    if not blocks_to_move:
        return False

    # Remove blocks from their current positions (in reverse to preserve indices)
    for start, end, _ in reversed(blocks_to_move):
        del lines[start:end + 1]
        # Remove any blank line left behind
        if start < len(lines) and lines[start].strip() == '' and start > 0 and lines[start - 1].strip() == '':
            del lines[start]

    # Insert all blocks just before whats-next (or before bibliography if no whats-next)
    insert_before = None
    for i, line in enumerate(lines):
        if 'class="whats-next"' in line:
            insert_before = i
            break
    if insert_before is None:
        for i, line in enumerate(lines):
            if 'class="bibliography"' in line:
                insert_before = i
                break
    if insert_before is None:
        return False

    insert_lines = []
    for _, _, block_lines in blocks_to_move:
        insert_lines.extend(block_lines)
        insert_lines.append('')

    for idx, ins_line in enumerate(insert_lines):
        lines.insert(insert_before + idx, ins_line)

    new_content = '\n'.join(lines)
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True

    return False


def main():
    book_root = Path('.')
    section_files = sorted(book_root.glob('part-*/module-*/section-*.html'))
    section_files += sorted(book_root.glob('appendices/appendix-*/section-*.html'))

    fixed = 0
    for f in section_files:
        if fix_file(f):
            fixed += 1
            print(f'Fixed: {f}')

    print(f'\nFixed {fixed} files')


if __name__ == '__main__':
    main()

"""Move code captions from above code blocks to below them.

Fixes the CAPTION_BEFORE_CODE pattern where a <div class="code-caption">
appears before a <pre> block instead of after it.

Pattern detected:
  <div class="code-caption">...</div>   <-- caption (wrong position)
  <pre><code>...</code></pre>            <-- code block
  [optional: <div class="code-output">...</div>]

Fixed to:
  <pre><code>...</code></pre>
  [optional: <div class="code-output">...</div>]
  <div class="code-caption">...</div>   <-- caption (correct position)
"""
import re
import sys
from pathlib import Path


def fix_file(filepath):
    """Fix caption positions in a single file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    original = content

    # Pattern: code-caption div followed within a few lines by a <pre> block
    # We need to move the caption to after the </pre> (and after any code-output)
    lines = content.split('\n')
    changed = False
    iterations = 0

    while iterations < 50:  # safety limit
        iterations += 1
        found = False

        for i in range(len(lines)):
            line = lines[i]

            # Detect a code-caption line
            if '<div class="code-caption">' not in line:
                continue

            # Find the caption block (may span multiple lines)
            caption_start = i
            caption_end = i
            if '</div>' in line:
                caption_end = i
            else:
                for j in range(i + 1, min(i + 10, len(lines))):
                    if '</div>' in lines[j]:
                        caption_end = j
                        break

            # Look ahead for a <pre> block within 5 lines after caption end
            pre_start = None
            for j in range(caption_end + 1, min(caption_end + 6, len(lines))):
                if '<pre' in lines[j]:
                    pre_start = j
                    break

            if pre_start is None:
                continue  # Caption is not before a code block

            # Find end of </pre>
            pre_end = None
            for j in range(pre_start, len(lines)):
                if '</pre>' in lines[j]:
                    pre_end = j
                    break

            if pre_end is None:
                continue

            # Check for code-output div after </pre>
            insert_after = pre_end
            for j in range(pre_end + 1, min(pre_end + 3, len(lines))):
                stripped = lines[j].strip()
                if not stripped:
                    continue
                if '<div class="code-output">' in stripped or 'class="code-output"' in stripped:
                    # Find end of code-output
                    for k in range(j, len(lines)):
                        if '</div>' in lines[k]:
                            insert_after = k
                            break
                    break
                else:
                    break

            # Extract caption lines
            caption_lines = lines[caption_start:caption_end + 1]

            # Remove caption from original position
            del lines[caption_start:caption_end + 1]

            # Adjust insert_after index (shifted by removal)
            removed_count = caption_end - caption_start + 1
            insert_after -= removed_count

            # Insert caption after code block (or code-output)
            for idx, cap_line in enumerate(caption_lines):
                lines.insert(insert_after + 1 + idx, cap_line)

            changed = True
            found = True
            break  # restart scan after modification

        if not found:
            break

    new_content = '\n'.join(lines)
    if new_content != original:
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

#!/usr/bin/env python3
"""Fix caption numbering across all section-*.html files.

Handles three categories of issues:

1. BARE NUMBERS in captions: "Code Fragment 5:" -> "Code Fragment X.Y.N:"
2. BARE NUMBERS in prose refs: "Code Fragment 5 below" -> "Code Fragment X.Y.N below"
3. BARE NUMBERS with letter suffixes: "Code Fragment 5b:" -> "Code Fragment X.Y.N:"
4. WRONG SECTION PREFIX: "Figure 28.1.2:" in section-32.1.html -> "Figure 32.1.2:"
   (also for Code Fragment and Table)

The section number X.Y is derived from the filename (section-X.Y.html).
N is a sequential counter within each section, per caption type.
"""

import os
import re
import glob
import sys


def extract_section_id(filename):
    """Extract section identifier from filename.

    section-4.2.html  -> '4.2'
    section-0.1.html  -> '0.1'
    section-a.1.html  -> 'A.1'
    section-fm.1.html -> 'FM.1'
    """
    basename = os.path.basename(filename)
    m = re.match(r'section-([a-zA-Z]+)\.(\d+)\.html', basename)
    if m:
        return f"{m.group(1).upper()}.{m.group(2)}"
    m = re.match(r'section-(\d+)\.(\d+)\.html', basename)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return None


def fix_file(filepath, dry_run=False):
    """Fix caption numbering in a single file. Returns list of changes made."""
    section_id = extract_section_id(filepath)
    if section_id is None:
        return []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        original = f.read()

    content = original
    changes = []

    # For each caption type, we need to:
    # A) Fix wrong-section X.Y.N references (where X.Y != current section)
    # B) Fix bare-number references (N: or N below or Nb:)

    for caption_type in ['Code Fragment', 'Figure', 'Table']:
        escaped = re.escape(caption_type)

        # --- PASS 1: Fix wrong-section-prefix in captions (strong tags) ---
        # Match: <strong>Code Fragment 28.1.2:</strong> where 28.1 != section_id
        # Also match in figcaption, diagram-caption, and caption elements
        wrong_prefix_pattern = re.compile(
            rf'({escaped}\s+)(\d+\.\d+)(\.\d+)'
        )

        def fix_wrong_prefix(m):
            prefix = m.group(1)
            old_sec = m.group(2)
            seq_part = m.group(3)  # e.g. ".2"
            if old_sec != section_id:
                return f"{prefix}{section_id}{seq_part}"
            return m.group(0)

        new_content = wrong_prefix_pattern.sub(fix_wrong_prefix, content)
        if new_content != content:
            # Count the changes
            for m in wrong_prefix_pattern.finditer(content):
                old_sec = m.group(2)
                if old_sec != section_id:
                    changes.append(
                        f"  {caption_type}: {old_sec}{m.group(3)} -> "
                        f"{section_id}{m.group(3)}"
                    )
            content = new_content

        # --- PASS 2: Fix bare numbers with optional letter suffix in captions ---
        # Pattern: <strong>Code Fragment 5b:</strong>
        # These appear in code-caption divs and similar caption containers
        bare_caption_pattern = re.compile(
            rf'(<strong>{escaped}\s+)(\d+)([a-z]*)(\s*:</strong>)'
        )

        # We need to assign sequential numbers. First collect all existing
        # properly-numbered captions to know what N values are taken.
        existing_pattern = re.compile(
            rf'{escaped}\s+{re.escape(section_id)}\.(\d+)'
        )
        existing_nums = set()
        for m in existing_pattern.finditer(content):
            existing_nums.add(int(m.group(1)))

        next_n = max(existing_nums) + 1 if existing_nums else 1

        def fix_bare_caption(m):
            nonlocal next_n
            prefix = m.group(1)
            suffix = m.group(4)
            new_ref = f"{prefix}{section_id}.{next_n}{suffix}"
            next_n += 1
            return new_ref

        new_content = bare_caption_pattern.sub(fix_bare_caption, content)
        if new_content != content:
            # Reset and redo to report changes
            next_n_report = max(existing_nums) + 1 if existing_nums else 1
            for m in bare_caption_pattern.finditer(content):
                old = f"{m.group(2)}{m.group(3)}"
                changes.append(
                    f"  {caption_type} caption: bare '{old}' -> "
                    f"{section_id}.{next_n_report}"
                )
                next_n_report += 1
            content = new_content

        # --- PASS 3: Fix bare numbers in prose references ---
        # Pattern: "Code Fragment 5 below" or "Code Fragment 23 below"
        # Also: "Code Fragment 5 shows" "Code Fragment 5 demonstrates"
        # Must NOT match "Code Fragment 5.2.1" (already has dots)
        bare_prose_pattern = re.compile(
            rf'({escaped}\s+)(\d+)([a-z]?)(\s+(?:below|above|shows?|demonstrates?|illustrates?|in practice))'
        )

        # For prose references, we need to map bare numbers to the correct
        # section-prefixed numbers. The bare number often corresponds to the
        # sequential position in the ENTIRE appendix or chapter.
        # We map them to the caption that follows in the same section.

        # Strategy: find all bare prose refs and replace with the next
        # available caption number that matches the section.
        # Actually, these bare refs typically refer to a caption in the
        # same section file. We need to figure out the mapping.

        # Let's collect the captions in order (already fixed from passes above)
        caption_order = re.compile(
            rf'{escaped}\s+{re.escape(section_id)}\.(\d+)\s*:'
        )
        caption_nums_in_order = [
            int(m.group(1)) for m in caption_order.finditer(content)
        ]

        # For each bare prose reference, try to map it to the Nth caption
        # in this section. If there's only one caption, map to it.
        bare_prose_matches = list(bare_prose_pattern.finditer(content))
        if bare_prose_matches:
            # Build replacement map: position of bare ref -> caption number
            # We map by order of appearance: first bare ref -> first caption, etc.
            # But we need to be smarter: the bare number might indicate which
            # caption it refers to. Let's check if the bare numbers are
            # sequential within the file.

            # Simple approach: map each bare prose ref to the next caption
            # that appears after it in the file
            replacements = []
            for bm in bare_prose_matches:
                bare_pos = bm.start()
                bare_num = bm.group(2) + bm.group(3)  # e.g. "5" or "5b"
                # Find the next caption after this position
                next_caption = None
                for cm in caption_order.finditer(content):
                    if cm.start() > bare_pos:
                        next_caption = int(cm.group(1))
                        break
                if next_caption is not None:
                    replacements.append((bm, next_caption))

            # Apply replacements in reverse order to preserve positions
            for bm, cap_num in reversed(replacements):
                old_text = bm.group(0)
                new_text = (
                    f"{bm.group(1)}{section_id}.{cap_num}{bm.group(4)}"
                )
                content = content[:bm.start()] + new_text + content[bm.end():]
                changes.append(
                    f"  {caption_type} prose ref: "
                    f"'{bm.group(2)}{bm.group(3)}' -> {section_id}.{cap_num}"
                )

    if content != original:
        if not dry_run:
            with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
        return changes
    return []


def main():
    dry_run = '--dry-run' in sys.argv
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    all_files = glob.glob(
        os.path.join(base_dir, '**', 'section-*.html'), recursive=True
    )
    all_files.sort()

    total_changes = 0
    files_changed = 0

    for filepath in all_files:
        rel_path = os.path.relpath(filepath, base_dir)
        changes = fix_file(filepath, dry_run=dry_run)
        if changes:
            files_changed += 1
            total_changes += len(changes)
            print(f"\n{rel_path}:")
            for c in changes:
                print(c)

    mode = " (DRY RUN)" if dry_run else ""
    print(f"\n{'='*60}")
    print(f"Summary{mode}:")
    print(f"  Files scanned:  {len(all_files)}")
    print(f"  Files changed:  {files_changed}")
    print(f"  Total changes:  {total_changes}")


if __name__ == '__main__':
    main()

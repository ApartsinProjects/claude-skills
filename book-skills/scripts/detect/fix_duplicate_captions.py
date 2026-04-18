#!/usr/bin/env python3
"""Remove duplicate code captions created by the auto-fix script.

The check_missing_code_captions.py --fix script sometimes inserted a
placeholder caption even when a proper caption already existed nearby.
This creates pairs of consecutive captions where the first is the
auto-generated placeholder and the second is the original.

This script detects consecutive code-caption pairs (within 3 lines)
and removes the shorter/less descriptive one.

Usage:
    python fix_duplicate_captions.py          # report only
    python fix_duplicate_captions.py --fix    # remove duplicates
"""

import re
import sys
from pathlib import Path


def find_duplicate_captions(filepath):
    """Find consecutive code-caption pairs in an HTML file."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    duplicates = []

    caption_lines = []
    for i, line in enumerate(lines):
        if 'class="code-caption"' in line:
            caption_lines.append(i)

    for j in range(len(caption_lines) - 1):
        idx_a = caption_lines[j]
        idx_b = caption_lines[j + 1]
        if idx_b - idx_a <= 3:
            # Determine which to remove: shorter description is the placeholder
            len_a = len(lines[idx_a])
            len_b = len(lines[idx_b])
            # The auto-generated one is typically shorter and has higher numbering
            # or contains "TODO:". Remove the shorter one.
            if "TODO:" in lines[idx_a]:
                remove_idx = idx_a
            elif "TODO:" in lines[idx_b]:
                remove_idx = idx_b
            elif len_a < len_b:
                remove_idx = idx_a
            else:
                remove_idx = idx_b
            duplicates.append({
                "line_a": idx_a + 1,
                "line_b": idx_b + 1,
                "remove_line": remove_idx + 1,
                "removed_text": lines[remove_idx].strip()[:120],
            })

    return duplicates


def fix_duplicates(filepath, duplicates):
    """Remove duplicate caption lines from file."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    # Collect 0-indexed line numbers to remove
    remove_indices = set()
    for d in duplicates:
        idx = d["remove_line"] - 1
        remove_indices.add(idx)
        # Also remove blank line after removed caption if present
        if idx + 1 < len(lines) and lines[idx + 1].strip() == "":
            remove_indices.add(idx + 1)

    new_lines = [line for i, line in enumerate(lines) if i not in remove_indices]
    filepath.write_text("\n".join(new_lines), encoding="utf-8")
    return len(duplicates)


def main():
    fix_mode = "--fix" in sys.argv
    book_root = Path(__file__).parent.parent.parent
    section_files = sorted(book_root.glob("part-*/module-*/section-*.html"))

    print(f"Scanning {len(section_files)} section files for duplicate captions...\n")

    total_dupes = 0
    total_fixed = 0
    findings = {}

    for filepath in section_files:
        dupes = find_duplicate_captions(filepath)
        if dupes:
            rel = filepath.relative_to(book_root)
            findings[str(rel)] = dupes
            total_dupes += len(dupes)

    if not findings:
        print("No duplicate captions found.")
        return

    print(f"Found {total_dupes} duplicate caption pairs across {len(findings)} files:\n")
    print("=" * 80)

    for filepath_str, items in sorted(findings.items()):
        print(f"\n{filepath_str}: {len(items)} duplicates")
        for item in items:
            print(f"  Lines {item['line_a']},{item['line_b']} -> remove line {item['remove_line']}")
            print(f"    {item['removed_text']}")

        if fix_mode:
            full_path = book_root / filepath_str
            count = fix_duplicates(full_path, items)
            total_fixed += count
            print(f"  -> Removed {count} duplicate captions")

    print(f"\n{'=' * 80}")
    print(f"Total: {total_dupes} duplicates in {len(findings)} files")
    if fix_mode:
        print(f"Fixed: {total_fixed} duplicate captions removed")
    else:
        print("Run with --fix to remove duplicates automatically")


if __name__ == "__main__":
    main()

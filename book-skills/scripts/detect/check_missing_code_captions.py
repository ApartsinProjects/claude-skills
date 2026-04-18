#!/usr/bin/env python3
"""Detect code blocks missing captions and optionally add placeholder captions.

Scans all section HTML files for <pre><code> blocks that are NOT followed
by a <div class="code-caption"> within the next few lines.

Usage:
    python check_missing_code_captions.py          # report only
    python check_missing_code_captions.py --fix     # add placeholder captions
"""

import re
import sys
from pathlib import Path

# Skip non-Python code blocks (shell installs, output blocks, YAML configs)
SKIP_LANGUAGES = {"language-bash", "language-shell", "language-text", "language-yaml",
                  "language-json", "language-html", "language-css", "language-xml",
                  "language-sql", "language-toml", "language-ini", "language-diff"}


def find_missing_captions(filepath):
    """Find code blocks without captions in an HTML file."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    missing = []

    for i, line in enumerate(lines):
        # Match opening <pre><code> or <pre class=...><code>
        m = re.search(r'<pre[^>]*><code\s+class="([^"]*)"', line)
        if not m:
            m = re.search(r'<pre[^>]*><code>', line)
            if not m:
                continue

        lang_class = m.group(1) if m.lastindex else ""

        # Skip non-Python languages
        if lang_class in SKIP_LANGUAGES:
            continue

        # Skip output blocks (class="language-text" or <pre class="language-text">)
        if "language-text" in line:
            continue

        # Find the closing </code></pre>
        close_line = i
        for j in range(i, min(i + 500, len(lines))):
            if "</code></pre>" in lines[j]:
                close_line = j
                break

        # Check if a code-caption follows within 5 lines after </code></pre>
        # or after a code-output div that follows the code block
        has_caption = False
        search_start = close_line
        for j in range(close_line, min(close_line + 6, len(lines))):
            if 'class="code-caption"' in lines[j]:
                has_caption = True
                break
            # If a code-output div follows, find its closing </div> first
            if 'class="code-output"' in lines[j]:
                # Find end of code-output block (search up to 200 lines)
                for k in range(j + 1, min(j + 200, len(lines))):
                    if "</div>" in lines[k]:
                        search_start = k
                        break
                # Now look for caption after code-output ends
                for k in range(search_start, min(search_start + 6, len(lines))):
                    if 'class="code-caption"' in lines[k]:
                        has_caption = True
                        break
                break

        if not has_caption:
            # Extract first comment line for context
            first_comment = ""
            for j in range(i, min(i + 5, len(lines))):
                cm = re.search(r'#\s*(.+)', lines[j])
                if cm:
                    first_comment = cm.group(1).strip()[:80]
                    break

            missing.append({
                "line": i + 1,
                "lang": lang_class or "unknown",
                "close_line": close_line + 1,
                "first_comment": first_comment,
            })

    return missing


def extract_section_number(filepath):
    """Extract section number from filename like section-34.5.html -> 34.5"""
    m = re.search(r'section-(\d+\.\d+)', filepath.name)
    return m.group(1) if m else "?.?"


def fix_missing_captions(filepath, missing_list):
    """Add placeholder code-caption divs after uncaptioned code blocks."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    section_num = extract_section_number(filepath)

    # Track existing caption count for numbering
    existing = len(re.findall(r'Code Fragment', content))
    next_num = existing + 1

    # Insert from bottom up to preserve line numbers
    for item in reversed(missing_list):
        close_idx = item["close_line"] - 1

        # Find the actual </code></pre> line
        insert_after = close_idx
        # Check if there's a code-output div right after
        for j in range(close_idx + 1, min(close_idx + 3, len(lines))):
            if 'class="code-output"' in lines[j]:
                # Find end of code-output
                for k in range(j, min(j + 20, len(lines))):
                    if "</div>" in lines[k]:
                        insert_after = k
                        break
                break

        desc = item["first_comment"] if item["first_comment"] else "TODO: add description"
        caption = (
            f'<div class="code-caption"><strong>Code Fragment {section_num}.{next_num}:</strong> '
            f'{desc}</div>'
        )
        lines.insert(insert_after + 1, caption)
        next_num += 1

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return len(missing_list)


def main():
    fix_mode = "--fix" in sys.argv
    book_root = Path(__file__).parent.parent.parent
    section_files = sorted(book_root.glob("part-*/module-*/section-*.html"))

    print(f"Scanning {len(section_files)} section files for missing code captions...\n")

    total_missing = 0
    total_fixed = 0
    findings_by_file = {}

    for filepath in section_files:
        missing = find_missing_captions(filepath)
        if missing:
            rel = filepath.relative_to(book_root)
            findings_by_file[str(rel)] = missing
            total_missing += len(missing)

    if not findings_by_file:
        print("All code blocks have captions.")
        return

    print(f"Found {total_missing} code blocks missing captions across {len(findings_by_file)} files:\n")
    print("=" * 80)

    for filepath_str, items in sorted(findings_by_file.items()):
        print(f"\n{filepath_str}: {len(items)} missing")
        for item in items:
            ctx = f' ({item["first_comment"]})' if item["first_comment"] else ""
            print(f"  Line {item['line']}: {item['lang']}{ctx}")

        if fix_mode:
            full_path = book_root / filepath_str
            count = fix_missing_captions(full_path, items)
            total_fixed += count
            print(f"  -> Fixed: added {count} placeholder captions")

    print(f"\n{'=' * 80}")
    print(f"Total: {total_missing} missing captions in {len(findings_by_file)} files")
    if fix_mode:
        print(f"Fixed: {total_fixed} placeholder captions added (search for TODO to refine)")
    else:
        print("Run with --fix to add placeholder captions automatically")


if __name__ == "__main__":
    main()

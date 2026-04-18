"""Remove redundant title text from inline SVG diagrams across the book.

Title criteria (matching the audit check SVG_TITLE_TEXT):
  - y attribute <= 45
  - font-size >= 13
  - font-weight is bold or 700
  - Text content has 3+ words

Only removes <text> elements inside top-level <svg> blocks.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {"vendor", "node_modules", ".git", "deprecated"}

# Regex to match a full <text ...>content</text> element on one line
TEXT_RE = re.compile(r'<text\b([^>]*)>([^<]{10,})</text>', re.IGNORECASE)
Y_RE = re.compile(r'\by=["\'](\d+(?:\.\d+)?)["\']')
FSIZE_RE = re.compile(r'\bfont-size=["\'](\d+(?:\.\d+)?)["\']')
BOLD_RE = re.compile(r'\bfont-weight=["\'](?:bold|[67]00)["\']')


def find_html_files(root):
    """Walk root and yield .html file paths, skipping excluded directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)


def is_inside_svg(full_text, pos):
    """Return True if character position `pos` is inside an <svg> block."""
    before = full_text[:pos]
    last_open = before.rfind("<svg")
    last_close = before.rfind("</svg>")
    return last_open > last_close


def is_inside_nested_svg(full_text, pos):
    """Return True if position is inside a nested (non-top-level) SVG element.

    Counts <svg> opens and </svg> closes before the position. If the depth
    at the position is >= 2, the element sits inside a nested SVG.
    """
    before = full_text[:pos]
    opens = [m.start() for m in re.finditer(r'<svg[\s>]', before)]
    closes = [m.start() for m in re.finditer(r'</svg>', before)]
    events = [(p, 'open') for p in opens] + [(p, 'close') for p in closes]
    events.sort()
    depth = 0
    for _, kind in events:
        if kind == 'open':
            depth += 1
        else:
            depth = max(depth - 1, 0)
    return depth >= 2


def is_title_text(attrs, text_content):
    """Check whether a <text> element matches title criteria."""
    y_match = Y_RE.search(attrs)
    fsize_match = FSIZE_RE.search(attrs)
    is_bold = bool(BOLD_RE.search(attrs))

    if not y_match or not fsize_match:
        return False

    y_val = float(y_match.group(1))
    fsize_val = float(fsize_match.group(1))

    if y_val > 45 or fsize_val < 13 or not is_bold:
        return False

    words = text_content.strip().split()
    return len(words) >= 3


def process_file(filepath):
    """Process one HTML file. Returns the number of titles removed."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    lines_to_remove = set()

    for i, line_text in enumerate(lines):
        for m in TEXT_RE.finditer(line_text):
            attrs = m.group(1)
            text_content = m.group(2)

            if not is_title_text(attrs, text_content):
                continue

            # Calculate character position of this line in the full content
            line_start = sum(len(lines[j]) + 1 for j in range(i))

            if not is_inside_svg(content, line_start):
                continue

            if is_inside_nested_svg(content, line_start):
                continue

            lines_to_remove.add(i)

    if not lines_to_remove:
        return 0

    new_lines = [ln for idx, ln in enumerate(lines) if idx not in lines_to_remove]
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(new_lines))

    return len(lines_to_remove)


def main():
    total_removed = 0
    files_changed = 0

    html_files = sorted(find_html_files(ROOT))
    print(f"Scanning {len(html_files)} HTML files...\n")

    for filepath in html_files:
        count = process_file(filepath)
        if count > 0:
            rel = os.path.relpath(filepath, ROOT)
            print(f"  {rel}: removed {count} title(s)")
            total_removed += count
            files_changed += 1

    print(f"\nDone. Removed {total_removed} redundant SVG title(s) from {files_changed} file(s).")
    return 0 if total_removed >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())

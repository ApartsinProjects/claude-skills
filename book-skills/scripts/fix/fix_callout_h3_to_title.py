#!/usr/bin/env python3
"""Convert any h3/h4 inside callout self-check divs to proper callout-title divs.

Catches all variants:
    <h3>Exercises</h3>
    <h3>&#10004; Knowledge Check</h3>
    <h3>&#x2714; Check Your Understanding</h3>
    etc.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}

# Match: callout self-check div followed by any h3/h4 on the next non-blank line
PATTERN = re.compile(
    r'(<div class="callout self-check">\s*\n\s*)'   # callout opening + whitespace
    r'<h[34]>[^<]*</h[34]>',                          # h3 or h4 with any text
    re.MULTILINE,
)


def replace_fn(m):
    prefix = m.group(1)
    return prefix + '<div class="callout-title">Self-Check</div>'


def main():
    fixed = 0
    for html_file in sorted(ROOT.rglob("*.html")):
        if any(s in html_file.parts for s in SKIP_DIRS):
            continue
        text = html_file.read_text(encoding="utf-8")
        if 'callout self-check' not in text:
            continue
        new_text = PATTERN.sub(replace_fn, text)
        if new_text != text:
            html_file.write_text(new_text, encoding="utf-8")
            print(f"Fixed: {html_file.relative_to(ROOT)}")
            fixed += 1

    print(f"\nConverted {fixed} files (h3/h4 in self-check -> callout-title)")


if __name__ == "__main__":
    main()

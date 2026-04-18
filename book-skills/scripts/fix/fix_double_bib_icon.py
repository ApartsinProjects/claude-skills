#!/usr/bin/env python3
"""Remove hardcoded emoji from bibliography-title divs (CSS ::before already adds the icon).

Fixes patterns like:
    <div class="bibliography-title">&#128218; References &amp; Further Reading</div>
to:
    <div class="bibliography-title">References &amp; Further Reading</div>
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}

# Match bibliography-title with leading emoji (HTML entity or literal)
PATTERN = re.compile(
    r'(class="bibliography-title"[^>]*>)\s*'
    r'(?:&#128218;|&#x1F4DA;|\U0001F4DA|📚)\s*'
)


def main():
    fixed = 0
    for html_file in sorted(ROOT.rglob("*.html")):
        if any(s in html_file.parts for s in SKIP_DIRS):
            continue
        text = html_file.read_text(encoding="utf-8")
        if 'bibliography-title' not in text:
            continue
        new_text = PATTERN.sub(r'\1', text)
        if new_text != text:
            html_file.write_text(new_text, encoding="utf-8")
            print(f"Fixed: {html_file.relative_to(ROOT)}")
            fixed += 1

    print(f"\nFixed {fixed} files (removed double bibliography icon)")


if __name__ == "__main__":
    main()

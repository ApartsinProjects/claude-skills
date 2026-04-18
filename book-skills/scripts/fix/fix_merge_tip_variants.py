#!/usr/bin/env python3
"""Merge practical-tip and best-practice callouts into tip.

Replaces:
    class="callout practical-tip"  ->  class="callout tip"
    class="callout best-practice"  ->  class="callout tip"

Also normalizes titles:
    >Practical Tip<  ->  >Tip<
    >Best Practice<  ->  >Tip<
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}

REPLACEMENTS = [
    ('class="callout practical-tip"', 'class="callout tip"'),
    ('class="callout best-practice"', 'class="callout tip"'),
    ('>Practical Tip<', '>Tip<'),
    ('>Best Practice<', '>Tip<'),
]


def main():
    fixed = 0
    for html_file in sorted(ROOT.rglob("*.html")):
        if any(s in html_file.parts for s in SKIP_DIRS):
            continue
        text = html_file.read_text(encoding="utf-8")
        if 'practical-tip' not in text and 'best-practice' not in text:
            continue
        original = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != original:
            html_file.write_text(text, encoding="utf-8")
            print(f"Fixed: {html_file.relative_to(ROOT)}")
            fixed += 1

    print(f"\nMerged {fixed} files (practical-tip/best-practice -> tip)")


if __name__ == "__main__":
    main()

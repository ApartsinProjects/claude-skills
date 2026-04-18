#!/usr/bin/env python3
"""Consolidate key-takeaway callouts to key-insight.

Replaces:
    <div class="callout key-takeaway">
        <div class="callout-title">Key Takeaway</div>
with:
    <div class="callout key-insight">
        <div class="callout-title">Key Insight</div>
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}


def main():
    fixed = 0
    for html_file in sorted(ROOT.rglob("*.html")):
        if any(s in html_file.parts for s in SKIP_DIRS):
            continue
        text = html_file.read_text(encoding="utf-8")
        if 'callout key-takeaway' not in text:
            continue
        new_text = text.replace(
            'class="callout key-takeaway"', 'class="callout key-insight"'
        ).replace(
            '>Key Takeaway<', '>Key Insight<'
        )
        if new_text != text:
            html_file.write_text(new_text, encoding="utf-8")
            print(f"Fixed: {html_file.relative_to(ROOT)}")
            fixed += 1

    print(f"\nConsolidated {fixed} files (key-takeaway -> key-insight)")


if __name__ == "__main__":
    main()

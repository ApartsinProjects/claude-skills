#!/usr/bin/env python3
"""Convert Knowledge Check h3 headers inside self-check callouts to proper callout-title divs.

Replaces patterns like:
    <h3>&#x1F4DD; Knowledge Check</h3>
    <h3>📝 Knowledge Check</h3>
With:
    <div class="callout-title">Self-Check</div>
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}

# Match h3 tags containing "Knowledge Check" with optional emoji/entity prefix
KNOWLEDGE_CHECK_RE = re.compile(
    r'<h3>\s*(?:&#x1F4DD;|&#128221;|\U0001F4DD|\U0001F4CE|📝|🔍|✅|&#x2705;|&#9989;)?\s*Knowledge Check\s*</h3>',
    re.IGNORECASE,
)


def main():
    fixed = 0
    for html_file in sorted(ROOT.rglob("*.html")):
        if any(s in html_file.parts for s in SKIP_DIRS):
            continue
        text = html_file.read_text(encoding="utf-8")
        if "Knowledge Check" not in text:
            continue
        new_text = KNOWLEDGE_CHECK_RE.sub(
            '<div class="callout-title">Self-Check</div>', text
        )
        if new_text != text:
            html_file.write_text(new_text, encoding="utf-8")
            print(f"Fixed: {html_file.relative_to(ROOT)}")
            fixed += 1

    print(f"\nConverted {fixed} files (Knowledge Check h3 -> callout-title Self-Check)")


if __name__ == "__main__":
    main()

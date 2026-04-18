"""Reorder structural elements in module index.html to canonical order.

Canonical order:
  1. epigraph
  2. illustration (optional)
  3. overview
  4. big-picture (optional)
  5. prereqs
  6. objectives
  7. sections-list
  8. whats-next
  9. bibliography (optional)

Strategy: extract prereqs div, remove from current position, insert before objectives.
"""
import re
from pathlib import Path

BOOK_ROOT = Path(r"E:\Projects\LLMCourse")
SKIP_DIRS = {"vendor", "node_modules", ".git", "deprecated", "__pycache__", "agents", "_archive", "templates"}

# Match the entire prereqs block
PREREQS_RE = re.compile(
    r'(\s*<div class="prereqs">.*?</div>\s*\n)',
    re.DOTALL,
)

# Match objectives block start
OBJECTIVES_START_RE = re.compile(r'(\s*<div class="objectives")')


def find_index_files():
    for f in BOOK_ROOT.rglob("index.html"):
        if any(s in f.parts for s in SKIP_DIRS):
            continue
        if "module-" in str(f):
            yield f


def main():
    fixed = 0

    for filepath in sorted(find_index_files()):
        html = filepath.read_text(encoding="utf-8")

        prereqs_m = PREREQS_RE.search(html)
        objectives_m = OBJECTIVES_START_RE.search(html)

        if not prereqs_m or not objectives_m:
            continue

        # Only fix if prereqs appears after objectives
        if prereqs_m.start() < objectives_m.start():
            continue

        # Extract prereqs block
        prereqs_block = prereqs_m.group(1)

        # Remove prereqs from current position
        html_without = html[:prereqs_m.start()] + html[prereqs_m.end():]

        # Find objectives position in the new html
        objectives_m2 = OBJECTIVES_START_RE.search(html_without)
        if not objectives_m2:
            continue

        # Insert prereqs before objectives
        insert_pos = objectives_m2.start()
        new_html = html_without[:insert_pos] + prereqs_block + html_without[insert_pos:]

        # Clean up triple blank lines
        new_html = re.sub(r'\n{3,}', '\n\n', new_html)

        filepath.write_text(new_html, encoding="utf-8")
        rel = filepath.relative_to(BOOK_ROOT)
        print(f"  {rel}: moved prereqs before objectives")
        fixed += 1

    print(f"\nFixed ordering in {fixed} files.")


if __name__ == "__main__":
    main()

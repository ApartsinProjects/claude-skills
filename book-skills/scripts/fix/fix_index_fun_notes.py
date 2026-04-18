"""Remove fun-note callouts from module index.html files.

Fun facts belong in section files, not chapter starters/indexes.
"""
import re
from pathlib import Path

BOOK_ROOT = Path(r"E:\Projects\LLMCourse")
SKIP_DIRS = {"vendor", "node_modules", ".git", "deprecated", "__pycache__", "agents", "_archive", "templates"}

# Match entire fun-note callout div (handles nested tags)
FUN_NOTE_RE = re.compile(
    r'\n?\s*<div class="callout fun-note">\s*'
    r'<div class="callout-title">Fun Fact</div>\s*'
    r'.*?'
    r'</div>\s*\n?',
    re.DOTALL,
)


def find_index_files():
    for f in BOOK_ROOT.rglob("index.html"):
        if any(s in f.parts for s in SKIP_DIRS):
            continue
        if "module-" in str(f):
            yield f


def main():
    total_removed = 0
    files_changed = 0

    for filepath in sorted(find_index_files()):
        html = filepath.read_text(encoding="utf-8")
        new_html, count = FUN_NOTE_RE.subn("", html)
        # Clean up any resulting double blank lines
        new_html = re.sub(r'\n{3,}', '\n\n', new_html)
        if count > 0:
            filepath.write_text(new_html, encoding="utf-8")
            rel = filepath.relative_to(BOOK_ROOT)
            print(f"  {rel}: removed {count} fun-note(s)")
            total_removed += count
            files_changed += 1

    print(f"\nRemoved {total_removed} fun-notes from {files_changed} index files.")


if __name__ == "__main__":
    main()

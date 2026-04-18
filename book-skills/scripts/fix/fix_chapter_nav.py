"""
Add chapter-nav bottom navigation to chapter index pages that are missing it.

Standard format:
<nav class="chapter-nav">
    <a href="PREV" class="prev">Previous Chapter</a>
    <a href="../index.html" class="up">Part Overview</a>
    <a href="NEXT" class="next">Next Chapter</a>
</nav>

Insert before </main> or before <footer>.
"""

import re
from pathlib import Path

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles"}

def find_chapter_indexes():
    """Find all module-*/index.html files."""
    files = []
    for f in BASE.rglob("index.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        # Must be inside a module-* directory
        if f.parent.name.startswith("module-") or f.parent.name.startswith("appendix-"):
            files.append(f)
    return sorted(files)

def get_siblings(filepath):
    """Get prev/next chapter directories."""
    parent = filepath.parent.parent  # part-X directory
    current = filepath.parent.name

    # Get all module dirs in this part
    if filepath.parent.name.startswith("module-"):
        siblings = sorted([
            d for d in parent.iterdir()
            if d.is_dir() and d.name.startswith("module-") and (d / "index.html").exists()
        ], key=lambda d: d.name)
    elif filepath.parent.name.startswith("appendix-"):
        siblings = sorted([
            d for d in parent.iterdir()
            if d.is_dir() and d.name.startswith("appendix-") and (d / "index.html").exists()
        ], key=lambda d: d.name)
    else:
        return None, None

    idx = None
    for i, s in enumerate(siblings):
        if s.name == current:
            idx = i
            break

    if idx is None:
        return None, None

    prev_href = f"../{siblings[idx-1].name}/index.html" if idx > 0 else None
    next_href = f"../{siblings[idx+1].name}/index.html" if idx < len(siblings) - 1 else None

    return prev_href, next_href

def fix_file(filepath):
    text = filepath.read_text(encoding="utf-8")

    # Skip if already has chapter-nav
    if 'class="chapter-nav"' in text:
        return False

    prev_href, next_href = get_siblings(filepath)

    # Build nav
    nav_parts = []
    if prev_href:
        nav_parts.append(f'    <a href="{prev_href}" class="prev">&larr; Previous Chapter</a>')
    else:
        nav_parts.append('    <span class="prev"></span>')

    nav_parts.append('    <a href="../index.html" class="up">Part Overview</a>')

    if next_href:
        nav_parts.append(f'    <a href="{next_href}" class="next">Next Chapter &rarr;</a>')
    else:
        nav_parts.append('    <span class="next"></span>')

    nav_block = '<nav class="chapter-nav">\n' + '\n'.join(nav_parts) + '\n</nav>\n'

    # Insert before <footer> or before </main>
    if "<footer>" in text:
        text = text.replace("<footer>", nav_block + "\n<footer>")
    elif "</main>" in text:
        text = text.replace("</main>", nav_block + "\n</main>")
    else:
        # Append before </body>
        text = text.replace("</body>", nav_block + "\n</body>")

    filepath.write_text(text, encoding="utf-8")
    return True

def main():
    files = find_chapter_indexes()
    print(f"Found {len(files)} chapter index files\n")

    fixed = 0
    for f in files:
        if fix_file(f):
            fixed += 1
            print(f"  Added chapter-nav: {f.relative_to(BASE)}")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {fixed} chapter index pages got chapter-nav")

if __name__ == "__main__":
    main()

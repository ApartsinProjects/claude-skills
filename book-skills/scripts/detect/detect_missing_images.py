"""
Detect all <img> tags that reference images that don't exist on disk.
Reports missing images grouped by HTML file with line numbers.
"""

import re
from pathlib import Path
from urllib.parse import unquote

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates"}

def find_html_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        files.append(f)
    return sorted(files)

def check_images(filepath):
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    missing = []

    for i, line in enumerate(lines, 1):
        for m in re.finditer(r'<img\s[^>]*src="([^"]+)"', line):
            src = m.group(1)
            # Skip data URIs and external URLs
            if src.startswith("data:") or src.startswith("http://") or src.startswith("https://"):
                continue
            # Resolve relative path
            img_path = (filepath.parent / unquote(src)).resolve()
            if not img_path.exists():
                missing.append((i, src, str(img_path)))

    return missing

def main():
    files = find_html_files()
    print(f"Scanning {len(files)} HTML files for missing images...\n")

    total_missing = 0
    files_with_missing = 0
    all_missing_srcs = []

    for f in files:
        missing = check_images(f)
        if missing:
            files_with_missing += 1
            rel = f.relative_to(BASE)
            print(f"  {rel}")
            for line_num, src, resolved in missing:
                print(f"    Line {line_num}: {src}")
                total_missing += 1
                all_missing_srcs.append((str(rel), src))

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_missing} missing images in {files_with_missing} files")

    # Group by image directory pattern
    dirs = {}
    for html_file, src in all_missing_srcs:
        d = str(Path(html_file).parent / Path(src).parent)
        dirs[d] = dirs.get(d, 0) + 1

    if dirs:
        print(f"\nMissing image directories:")
        for d, count in sorted(dirs.items(), key=lambda x: -x[1]):
            print(f"  {d}: {count} images")

if __name__ == "__main__":
    main()

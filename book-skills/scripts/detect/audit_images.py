"""
Audit image coverage across the LLM Course textbook.

Reports:
1. Image files that exist but are NOT referenced by any HTML page
2. HTML pages that have ZERO <img> or <svg> illustrations
3. Broken image references (HTML references files that don't exist)
"""

import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"E:\Projects\LLMCourse")
SKIP_DIRS = {"vendor", "node_modules", ".git", "__pycache__", "scripts", "_lab_fragments"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


def should_skip(fpath: Path) -> bool:
    parts = fpath.relative_to(ROOT).parts
    return any(p in SKIP_DIRS for p in parts)


def find_all_images() -> set:
    """Find all image files in the project."""
    images = set()
    for ext in IMAGE_EXTS:
        for f in ROOT.rglob(f"*{ext}"):
            if not should_skip(f):
                images.add(f)
    return images


def find_all_html() -> list:
    """Find all HTML files."""
    files = []
    for f in sorted(ROOT.rglob("*.html")):
        if not should_skip(f):
            files.append(f)
    return files


def extract_img_refs(fpath: Path, text: str) -> list:
    """Extract image references from HTML file."""
    refs = []
    # <img src="...">
    for m in re.finditer(r'<img\s[^>]*src="([^"]+)"', text):
        refs.append(m.group(1))
    # background-image: url(...)
    for m in re.finditer(r'url\(["\']?([^)"\']+)["\']?\)', text):
        src = m.group(1)
        if any(src.lower().endswith(ext) for ext in IMAGE_EXTS):
            refs.append(src)
    return refs


def resolve_ref(html_path: Path, ref: str) -> Path:
    """Resolve a relative image reference to an absolute path."""
    if ref.startswith("http://") or ref.startswith("https://") or ref.startswith("data:"):
        return None
    return (html_path.parent / ref).resolve()


def has_inline_svg(text: str) -> bool:
    """Check if the page has inline SVG diagrams (not just icons)."""
    # Count substantial SVGs (more than just a small icon)
    svgs = re.findall(r'<svg\s[^>]*>(.*?)</svg>', text, re.DOTALL)
    for svg_content in svgs:
        # Skip tiny SVGs (likely icons) - check if it has paths/rects/circles
        elements = len(re.findall(r'<(path|rect|circle|line|polygon|polyline|text|g)\s', svg_content))
        if elements >= 3:
            return True
    return False


def main():
    print("=" * 70)
    print("IMAGE COVERAGE AUDIT")
    print("=" * 70)

    all_images = find_all_images()
    all_html = find_all_html()

    print(f"\nFound {len(all_images)} image files")
    print(f"Found {len(all_html)} HTML files")

    # Track which images are referenced
    referenced_images = set()
    # Track pages with no illustrations
    pages_no_images = []
    # Track broken references
    broken_refs = []
    # Track per-page image counts
    page_image_counts = {}

    for fpath in all_html:
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        refs = extract_img_refs(fpath, text)
        has_svg = has_inline_svg(text)

        resolved = []
        for ref in refs:
            abs_path = resolve_ref(fpath, ref)
            if abs_path is None:
                continue  # external URL
            resolved.append(abs_path)
            if abs_path.exists():
                referenced_images.add(abs_path)
            else:
                broken_refs.append((fpath, ref, abs_path))

        total_illustrations = len(resolved) + (1 if has_svg else 0)
        rel = fpath.relative_to(ROOT)
        page_image_counts[str(rel)] = total_illustrations

        if total_illustrations == 0:
            # Only flag content pages (sections), not index/toc pages
            name = fpath.name
            if name.startswith("section-") or name.startswith("requirements"):
                pages_no_images.append(fpath)

    # Report 1: Orphaned images
    orphaned = all_images - referenced_images
    print(f"\n{'=' * 70}")
    print(f"ORPHANED IMAGES (exist but not referenced): {len(orphaned)}")
    print(f"{'=' * 70}")
    if orphaned:
        by_dir = defaultdict(list)
        for img in sorted(orphaned):
            rel = img.relative_to(ROOT)
            by_dir[str(rel.parent)].append(rel.name)
        for d in sorted(by_dir):
            print(f"\n  {d}/")
            for name in sorted(by_dir[d]):
                print(f"    {name}")

    # Report 2: Pages with no illustrations
    print(f"\n{'=' * 70}")
    print(f"CONTENT PAGES WITH NO ILLUSTRATIONS: {len(pages_no_images)}")
    print(f"{'=' * 70}")
    by_part = defaultdict(list)
    for fpath in pages_no_images:
        rel = fpath.relative_to(ROOT)
        parts = rel.parts
        if len(parts) >= 2:
            by_part[parts[0]].append(str(rel))
        else:
            by_part["root"].append(str(rel))
    for part in sorted(by_part):
        print(f"\n  {part}/")
        for page in sorted(by_part[part]):
            print(f"    {page}")

    # Report 3: Broken references
    print(f"\n{'=' * 70}")
    print(f"BROKEN IMAGE REFERENCES: {len(broken_refs)}")
    print(f"{'=' * 70}")
    for fpath, ref, abs_path in sorted(broken_refs, key=lambda x: str(x[0])):
        rel = fpath.relative_to(ROOT)
        print(f"  {rel}: {ref}")

    # Summary stats
    total_content = sum(1 for f in all_html if f.name.startswith("section-"))
    with_images = total_content - sum(1 for f in pages_no_images if f.name.startswith("section-"))
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total image files:          {len(all_images)}")
    print(f"  Referenced image files:      {len(referenced_images)}")
    print(f"  Orphaned image files:        {len(orphaned)}")
    print(f"  Total content sections:      {total_content}")
    print(f"  Sections with illustrations: {with_images}")
    print(f"  Sections without:            {total_content - with_images}")
    print(f"  Broken image references:     {len(broken_refs)}")
    pct = (with_images / total_content * 100) if total_content else 0
    print(f"  Coverage:                    {pct:.1f}%")


if __name__ == "__main__":
    main()

"""
Audit for duplicate/excessive images per section.

Reports:
1. Sections with more than 4 images (potentially too many)
2. Sections where multiple images convey the same concept (filename similarity)
3. Images that were just linked by the orphan-linking script (inserted via <figure> tags)
   that may duplicate existing inline SVG diagrams
"""

import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"E:\Projects\LLMCourse")
SKIP_DIRS = {"vendor", "node_modules", ".git", "__pycache__", "scripts", "_lab_fragments"}


def should_skip(fpath: Path) -> bool:
    parts = fpath.relative_to(ROOT).parts
    return any(p in SKIP_DIRS for p in parts)


def extract_images(text: str) -> list:
    """Extract all image references with context."""
    images = []
    for m in re.finditer(r'<img\s[^>]*src="([^"]+)"[^>]*>', text):
        src = m.group(1)
        # Get surrounding context (caption or alt)
        alt_m = re.search(r'alt="([^"]*)"', m.group(0))
        alt = alt_m.group(1) if alt_m else ""
        # Check if inside a <figure>
        start = max(0, m.start() - 200)
        context = text[start:m.end() + 200]
        in_figure = "<figure>" in context or "<figure " in context
        # Check if inside a callout
        in_callout = 'class="callout' in text[max(0, m.start()-500):m.start()]
        images.append({
            "src": src,
            "alt": alt,
            "in_figure": in_figure,
            "in_callout": in_callout,
            "pos": m.start()
        })
    return images


def count_inline_svgs(text: str) -> int:
    """Count substantial inline SVG diagrams."""
    count = 0
    for m in re.finditer(r'<svg\s[^>]*>(.*?)</svg>', text, re.DOTALL):
        elements = len(re.findall(r'<(path|rect|circle|line|polygon|polyline|text|g)\s', m.group(1)))
        if elements >= 3:
            count += 1
    return count


def keyword_overlap(img1: dict, img2: dict) -> float:
    """Compute keyword overlap between two image filenames."""
    def keywords(src):
        stem = Path(src).stem.lower()
        words = set(re.split(r'[-_]', stem))
        stop = {'the', 'and', 'for', 'with', 'from', 'png', 'jpg', 'img', 'figure', 'diagram'}
        return {w for w in words if len(w) > 2 and w not in stop}

    k1 = keywords(img1["src"])
    k2 = keywords(img2["src"])
    if not k1 or not k2:
        return 0
    return len(k1 & k2) / min(len(k1), len(k2))


def main():
    print("=" * 70)
    print("DUPLICATE / EXCESSIVE IMAGE AUDIT")
    print("=" * 70)

    excessive = []
    duplicates = []
    total_sections = 0
    total_images = 0

    for fpath in sorted(ROOT.rglob("section-*.html")):
        if should_skip(fpath):
            continue
        # Skip appendices
        rel = fpath.relative_to(ROOT)
        if "appendix" in str(rel) or "appendices" in str(rel):
            continue

        total_sections += 1
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        images = extract_images(text)
        svg_count = count_inline_svgs(text)
        total_visuals = len(images) + svg_count
        total_images += len(images)

        # Flag excessive
        if total_visuals > 4:
            excessive.append((rel, len(images), svg_count, total_visuals))

        # Check for keyword duplicates
        for i in range(len(images)):
            for j in range(i + 1, len(images)):
                overlap = keyword_overlap(images[i], images[j])
                if overlap >= 0.5:
                    duplicates.append((rel, images[i]["src"], images[j]["src"], overlap))

    # Report
    print(f"\nScanned {total_sections} section files, {total_images} <img> references total")

    print(f"\n{'=' * 70}")
    print(f"SECTIONS WITH MORE THAN 4 VISUALS (images + SVGs): {len(excessive)}")
    print(f"{'=' * 70}")
    for rel, img_count, svg_count, total in sorted(excessive, key=lambda x: -x[3]):
        print(f"  {rel}: {img_count} images + {svg_count} SVGs = {total} total")

    print(f"\n{'=' * 70}")
    print(f"POTENTIAL DUPLICATE IMAGES (keyword overlap >= 50%): {len(duplicates)}")
    print(f"{'=' * 70}")
    for rel, src1, src2, overlap in sorted(duplicates, key=lambda x: -x[3]):
        print(f"  {rel}:")
        print(f"    {Path(src1).name}  <->  {Path(src2).name}  (overlap: {overlap:.0%})")


if __name__ == "__main__":
    main()

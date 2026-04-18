#!/usr/bin/env python3
"""TASK-011: SVG Quality and Correctness Audit for LLMCourse textbook.

Scans all HTML files for inline SVG diagrams, parses quality indicators,
scores each SVG, and flags the worst-scoring ones for rebuild.
"""

import os
import re
import sys
from pathlib import Path
from collections import Counter

# ── Configuration ──────────────────────────────────────────────────────

ROOT = Path(r"E:\Projects\LLMCourse")

EXCLUDE_DIRS = {
    "_scripts_archive", "node_modules", ".claude", "scripts",
    "templates", "styles", "agents", "_lab_fragments", "vendor",
}

# ── Helpers ────────────────────────────────────────────────────────────

def collect_html_files(root: Path) -> list[Path]:
    """Walk the project tree and collect .html files, skipping excluded dirs."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories (in-place so os.walk skips them)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".html"):
                results.append(Path(dirpath) / fn)
    return sorted(results)


def extract_svgs(html_text: str) -> list[str]:
    """Return all top-level <svg ...>...</svg> blocks from an HTML string."""
    # Use a simple regex that handles nested tags reasonably
    pattern = re.compile(r"<svg\b[^>]*>.*?</svg>", re.DOTALL)
    return pattern.findall(html_text)


def parse_viewbox(svg: str) -> tuple[float, float, float, float] | None:
    m = re.search(r'viewBox="([^"]+)"', svg)
    if not m:
        return None
    parts = m.group(1).split()
    if len(parts) != 4:
        return None
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        return None


def count_elements(svg: str) -> dict[str, int]:
    tags = ["rect", "circle", "ellipse", "path", "line", "polygon", "polyline", "text"]
    counts = {}
    for tag in tags:
        # Count opening tags for each element type
        counts[tag] = len(re.findall(rf"<{tag}\b", svg))
    counts["total"] = sum(counts.values())
    return counts


def has_gradients(svg: str) -> bool:
    return bool(re.search(r"<(linearGradient|radialGradient)\b", svg))


def has_drop_shadows(svg: str) -> bool:
    return bool(re.search(r"<(filter|feDropShadow|feGaussianBlur)\b", svg))


def has_rounded_corners(svg: str) -> bool:
    return bool(re.search(r'\brx="', svg))


def has_round_linecap(svg: str) -> bool:
    return bool(re.search(r'stroke-linecap="round"', svg))


def has_dashed_lines(svg: str) -> bool:
    return bool(re.search(r'stroke-dasharray', svg))


def get_font_sizes(svg: str) -> list[float]:
    sizes = []
    for m in re.finditer(r'font-size="([^"]+)"', svg):
        try:
            val = float(m.group(1).replace("px", ""))
            sizes.append(val)
        except ValueError:
            pass
    return sizes


def has_tiny_fonts(svg: str) -> bool:
    sizes = get_font_sizes(svg)
    return any(s < 10 for s in sizes)


def min_font_size(svg: str) -> float | None:
    sizes = get_font_sizes(svg)
    return min(sizes) if sizes else None


def unique_fill_colors(svg: str) -> set[str]:
    colors = set()
    for m in re.finditer(r'fill="([^"]+)"', svg):
        c = m.group(1).strip().lower()
        if c not in ("none", "transparent", ""):
            colors.add(c)
    return colors


def get_caption(html: str, svg_start: int) -> str:
    """Try to extract the diagram-caption following this SVG."""
    after = html[svg_start:]
    m = re.search(r'<div class="diagram-caption">(.*?)</div>', after, re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()[:120]
    return ""


# ── Scoring ────────────────────────────────────────────────────────────

def score_svg(info: dict) -> tuple[int, str]:
    """Score an SVG from 0..100. Return (score, grade)."""
    pts = 0

    # Element richness (up to 20 pts)
    total_els = info["element_counts"]["total"]
    if total_els >= 20:
        pts += 20
    elif total_els >= 12:
        pts += 15
    elif total_els >= 6:
        pts += 10
    elif total_els >= 3:
        pts += 5

    # Gradients (10 pts)
    if info["has_gradients"]:
        pts += 10

    # Drop shadows (10 pts)
    if info["has_drop_shadows"]:
        pts += 10

    # Rounded corners (8 pts)
    if info["has_rounded_corners"]:
        pts += 8

    # Round linecap (5 pts)
    if info["has_round_linecap"]:
        pts += 5

    # Dashed lines for annotations (5 pts)
    if info["has_dashed_lines"]:
        pts += 5

    # No tiny fonts (7 pts, penalty if present)
    if not info["has_tiny_fonts"]:
        pts += 7

    # Color diversity (up to 15 pts)
    n_colors = info["n_unique_colors"]
    if n_colors >= 6:
        pts += 15
    elif n_colors >= 4:
        pts += 10
    elif n_colors >= 2:
        pts += 5

    # Reasonable aspect ratio (up to 10 pts)
    vb = info["viewbox"]
    if vb:
        w, h = vb[2] - vb[0], vb[3] - vb[1]
        if h > 0:
            ratio = w / h
            if 0.5 <= ratio <= 4.0:
                pts += 10
            elif 0.3 <= ratio <= 6.0:
                pts += 5

    # Reasonable viewBox size (up to 10 pts)
    if vb:
        w, h = vb[2] - vb[0], vb[3] - vb[1]
        area = w * h
        if area >= 100000:
            pts += 10
        elif area >= 40000:
            pts += 7
        elif area >= 10000:
            pts += 4

    # Grade
    if pts >= 75:
        grade = "EXCELLENT"
    elif pts >= 55:
        grade = "GOOD"
    elif pts >= 35:
        grade = "ADEQUATE"
    else:
        grade = "POOR"

    return pts, grade


# ── Main ───────────────────────────────────────────────────────────────

def main():
    html_files = collect_html_files(ROOT)
    print(f"Scanning {len(html_files)} HTML files for inline SVG diagrams...\n")

    all_svgs = []  # list of dicts

    for fpath in html_files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        svgs = extract_svgs(text)
        for idx, svg_text in enumerate(svgs):
            # Find position in original text for caption extraction
            svg_start = text.find(svg_text)
            caption = get_caption(text, svg_start) if svg_start >= 0 else ""

            vb = parse_viewbox(svg_text)
            el_counts = count_elements(svg_text)
            fill_colors = unique_fill_colors(svg_text)
            font_sizes = get_font_sizes(svg_text)

            info = {
                "file": str(fpath.relative_to(ROOT)),
                "svg_index": idx + 1,
                "caption": caption,
                "viewbox": vb,
                "element_counts": el_counts,
                "has_gradients": has_gradients(svg_text),
                "has_drop_shadows": has_drop_shadows(svg_text),
                "has_rounded_corners": has_rounded_corners(svg_text),
                "has_round_linecap": has_round_linecap(svg_text),
                "has_dashed_lines": has_dashed_lines(svg_text),
                "has_tiny_fonts": has_tiny_fonts(svg_text),
                "min_font_size": min_font_size(svg_text),
                "n_unique_colors": len(fill_colors),
                "fill_colors": fill_colors,
                "font_sizes": sorted(set(font_sizes)),
                "svg_length": len(svg_text),
            }
            pts, grade = score_svg(info)
            info["score"] = pts
            info["grade"] = grade
            all_svgs.append(info)

    # ── Summary statistics ─────────────────────────────────────────
    print(f"Found {len(all_svgs)} inline SVG diagrams across {len(html_files)} HTML files.\n")

    grade_counts = Counter(s["grade"] for s in all_svgs)
    print("Grade distribution:")
    for g in ["EXCELLENT", "GOOD", "ADEQUATE", "POOR"]:
        print(f"  {g:12s}: {grade_counts.get(g, 0):4d}")
    print()

    scores = [s["score"] for s in all_svgs]
    if scores:
        print(f"Score range: {min(scores)} .. {max(scores)}  (mean: {sum(scores)/len(scores):.1f})")
    print()

    # ── Quality indicator summary ──────────────────────────────────
    n = len(all_svgs)
    print("Quality indicator prevalence:")
    for key in ["has_gradients", "has_drop_shadows", "has_rounded_corners",
                "has_round_linecap", "has_dashed_lines", "has_tiny_fonts"]:
        count = sum(1 for s in all_svgs if s[key])
        pct = 100 * count / n if n else 0
        label = key.replace("has_", "").replace("_", " ").title()
        print(f"  {label:25s}: {count:4d} / {n}  ({pct:5.1f}%)")
    print()

    # ── Sorted list: all SVGs by score ─────────────────────────────
    all_svgs.sort(key=lambda s: (s["score"], s["file"]))

    print("=" * 100)
    print("FULL AUDIT (sorted by score, worst first)")
    print("=" * 100)

    for i, s in enumerate(all_svgs, 1):
        vb_str = ""
        if s["viewbox"]:
            vb = s["viewbox"]
            vb_str = f"{vb[2]-vb[0]:.0f}x{vb[3]-vb[1]:.0f}"
        flags = []
        if s["has_gradients"]:
            flags.append("grad")
        if s["has_drop_shadows"]:
            flags.append("shadow")
        if s["has_rounded_corners"]:
            flags.append("rounded")
        if s["has_round_linecap"]:
            flags.append("linecap")
        if s["has_dashed_lines"]:
            flags.append("dashed")
        if s["has_tiny_fonts"]:
            flags.append("TINY-FONT")

        print(f"{i:3d}. [{s['grade']:9s}] score={s['score']:3d}  "
              f"els={s['element_counts']['total']:3d}  "
              f"colors={s['n_unique_colors']:2d}  "
              f"vb={vb_str:>9s}  "
              f"flags=[{', '.join(flags)}]")
        print(f"     File: {s['file']}  (SVG #{s['svg_index']})")
        if s["caption"]:
            print(f"     Caption: {s['caption']}")
        print()

    # ── Bottom 13: worst SVGs ──────────────────────────────────────
    worst = all_svgs[:13]
    print()
    print("=" * 100)
    print("BOTTOM 13: WORST SVGs FLAGGED FOR REBUILD")
    print("=" * 100)
    for i, s in enumerate(worst, 1):
        vb_str = ""
        if s["viewbox"]:
            vb = s["viewbox"]
            vb_str = f"{vb[2]-vb[0]:.0f}x{vb[3]-vb[1]:.0f}"
        reasons = []
        if not s["has_gradients"]:
            reasons.append("no gradients")
        if not s["has_drop_shadows"]:
            reasons.append("no shadows")
        if not s["has_rounded_corners"]:
            reasons.append("no rounded corners")
        if not s["has_round_linecap"]:
            reasons.append("no round linecap")
        if not s["has_dashed_lines"]:
            reasons.append("no dashed lines")
        if s["has_tiny_fonts"]:
            reasons.append(f"tiny font ({s['min_font_size']}px)")
        if s["n_unique_colors"] < 3:
            reasons.append(f"only {s['n_unique_colors']} colors")
        if s["element_counts"]["total"] < 6:
            reasons.append(f"only {s['element_counts']['total']} elements")

        print(f"\n  #{i}  Score: {s['score']}  Grade: {s['grade']}")
        print(f"  File: {s['file']}  (SVG #{s['svg_index']}, viewBox {vb_str})")
        if s["caption"]:
            print(f"  Caption: {s['caption']}")
        print(f"  Issues: {'; '.join(reasons)}")


if __name__ == "__main__":
    main()

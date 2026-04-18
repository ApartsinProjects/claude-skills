#!/usr/bin/env python3
"""Fix SVG text clipping by expanding viewBox to accommodate text near edges.

Finds all HTML files, parses SVG elements, checks text element coordinates
against viewBox boundaries, and expands the viewBox when text is within a
configurable margin of the edges. Only modifies the viewBox attribute;
text elements are never moved.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARGIN = 15  # units of proximity that count as "near edge"
PADDING = 20  # extra padding added when expanding viewBox

# Files/SVGs to skip: 28x28 icons in pathways/index.html are intentional
SKIP_FILES = {
    os.path.normpath("front-matter/pathways/index.html"),
}

# Regex patterns
SVG_RE = re.compile(
    r'(<svg\b[^>]*viewBox=["\'])([^"\']+)(["\'][^>]*>)(.*?)</svg>',
    re.DOTALL,
)
TEXT_TAG_RE = re.compile(r'<text\b[^>]*>')
COORD_RE = {
    "x": re.compile(r'\bx=["\'](-?[\d.]+)'),
    "y": re.compile(r'\by=["\'](-?[\d.]+)'),
}
FONT_SIZE_RE = re.compile(r'\bfont-size=["\'](\d+)')


def parse_viewbox(vb_str):
    """Parse 'minX minY width height' into four floats."""
    parts = vb_str.split()
    if len(parts) != 4:
        return None
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


def format_viewbox(vals):
    """Format four floats back into a viewBox string, using ints where possible."""
    formatted = []
    for v in vals:
        if v == int(v):
            formatted.append(str(int(v)))
        else:
            formatted.append(f"{v:.1f}")
    return " ".join(formatted)


def get_text_bounds(svg_body):
    """Extract all text element coordinate bounds from an SVG body.

    Returns (min_x, min_y, max_x, max_y) across all text elements,
    accounting for font size as approximate text height.
    """
    xs = []
    ys = []
    for tag_match in TEXT_TAG_RE.finditer(svg_body):
        tag = tag_match.group(0)
        x_m = COORD_RE["x"].search(tag)
        y_m = COORD_RE["y"].search(tag)
        if not x_m or not y_m:
            continue
        x = float(x_m.group(1))
        y = float(y_m.group(1))
        fs_m = FONT_SIZE_RE.search(tag)
        font_size = float(fs_m.group(1)) if fs_m else 12
        # Text is rendered with y as the baseline; it extends upward by ~font_size
        # and to the sides depending on anchor. We treat x,y as the point to protect.
        xs.append(x)
        ys.append(y)
        # Also consider that text extends above the baseline
        ys.append(y - font_size)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def compute_new_viewbox(vb, svg_body):
    """Compute an expanded viewBox if text elements are near/outside edges.

    Returns (new_viewbox_string, changes_list) or (None, []) if no change needed.
    """
    minX, minY, w, h = vb
    maxX = minX + w
    maxY = minY + h

    bounds = get_text_bounds(svg_body)
    if bounds is None:
        return None, []

    text_minX, text_minY, text_maxX, text_maxY = bounds

    changes = []
    new_minX = minX
    new_minY = minY
    new_maxX = maxX
    new_maxY = maxY

    # Check left edge: if text x is near or past the left boundary
    if text_minX < minX + MARGIN:
        new_minX = text_minX - PADDING
        changes.append(f"left: text at x={text_minX:.0f}, minX {minX:.0f} -> {new_minX:.0f}")

    # Check top edge: if text y (accounting for font ascent) is near or past the top
    if text_minY < minY + MARGIN:
        new_minY = text_minY - PADDING
        changes.append(f"top: text at y={text_minY:.0f}, minY {minY:.0f} -> {new_minY:.0f}")

    # Check right edge
    if text_maxX > maxX - MARGIN:
        new_maxX = text_maxX + PADDING
        changes.append(f"right: text at x={text_maxX:.0f}, maxX {maxX:.0f} -> {new_maxX:.0f}")

    # Check bottom edge
    if text_maxY > maxY - MARGIN:
        new_maxY = text_maxY + PADDING
        changes.append(f"bottom: text at y={text_maxY:.0f}, maxY {maxY:.0f} -> {new_maxY:.0f}")

    if not changes:
        return None, []

    new_w = new_maxX - new_minX
    new_h = new_maxY - new_minY
    return format_viewbox([new_minX, new_minY, new_w, new_h]), changes


def process_file(filepath, rel_path):
    """Process a single HTML file. Returns list of change descriptions."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    all_changes = []
    new_content = content
    offset = 0

    for match in SVG_RE.finditer(content):
        prefix = match.group(1)   # '<svg ... viewBox="'
        vb_str = match.group(2)   # the viewBox value
        suffix = match.group(3)   # '" ...>'
        svg_body = match.group(4)

        vb = parse_viewbox(vb_str)
        if vb is None:
            continue

        new_vb_str, changes = compute_new_viewbox(vb, svg_body)
        if new_vb_str is None:
            continue

        # Replace the viewBox value in the content
        start = match.start(2) + offset
        end = match.end(2) + offset
        new_content = new_content[:start] + new_vb_str + new_content[end:]
        offset += len(new_vb_str) - len(vb_str)

        for c in changes:
            desc = f"  viewBox '{vb_str}' -> '{new_vb_str}': {c}"
            all_changes.append(desc)

    if all_changes:
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)

    return all_changes


def main():
    files_modified = 0
    total_svgs_fixed = 0

    for root, dirs, files in os.walk(ROOT):
        # Skip .git and node_modules
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        for fname in sorted(files):
            if not fname.endswith(".html"):
                continue
            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, ROOT)
            norm_rel = os.path.normpath(rel_path)

            # Skip excluded files
            if norm_rel in SKIP_FILES:
                continue

            changes = process_file(filepath, rel_path)
            if changes:
                files_modified += 1
                svg_count = len(set(c.split(":")[0] for c in changes))
                total_svgs_fixed += svg_count
                print(f"\n{rel_path}")
                for c in changes:
                    print(c)

    print(f"\n{'='*60}")
    print(f"Files modified: {files_modified}")
    print(f"Total viewBox expansions: {total_svgs_fixed}")


if __name__ == "__main__":
    main()

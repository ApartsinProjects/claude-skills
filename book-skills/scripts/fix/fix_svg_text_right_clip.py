"""Fix SVG text clipping at the right edge by widening the viewBox.

For each SVG, compute the maximum right extent of all start-anchored text elements.
If any text overflows the viewBox width, widen the viewBox to fit.
"""
import re
from pathlib import Path

SVG_OPEN = re.compile(r'(<svg\b[^>]*viewBox\s*=\s*")([^"]+)(")', re.IGNORECASE)
SVG_CLOSE = re.compile(r'</svg>', re.IGNORECASE)
TEXT_EL = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.IGNORECASE | re.DOTALL)
ATTR_X = re.compile(r'\bx\s*=\s*"([^"]+)"')
ATTR_ANCHOR = re.compile(r'text-anchor\s*=\s*"([^"]+)"')
ATTR_FONT_SIZE = re.compile(r'font-size\s*=\s*"([^"]+)"')
ATTR_FONT_WEIGHT = re.compile(r'font-weight\s*=\s*"(bold|[6-9]\d\d)"')

CHAR_WIDTH_FACTOR = 0.6  # slightly generous to avoid marginal clips
BOLD_FACTOR = 1.08
PADDING = 10  # extra padding beyond text


def estimate_text_width(content, font_size, is_bold):
    clean = re.sub(r'<[^>]+>', '', content)
    # Decode common HTML entities for length estimation
    clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    clean = clean.replace('&rarr;', '>').replace('&#8226;', '*')
    clean = re.sub(r'&[a-z]+;', 'X', clean)
    clean = re.sub(r'&#\d+;', 'X', clean)
    clean = clean.strip()
    w = len(clean) * font_size * CHAR_WIDTH_FACTOR
    if is_bold:
        w *= BOLD_FACTOR
    return w


files_fixed = 0
total_svgs_widened = 0

for f in Path(".").rglob("*.html"):
    if any(skip in str(f) for skip in ["vendor", ".git", "node_modules", "deprecated"]):
        continue

    text = f.read_text(encoding="utf-8")
    if '<svg' not in text.lower():
        continue

    lines = text.split("\n")
    changed = False

    # First pass: identify SVG blocks and their text extents
    svg_blocks = []  # (start_line, vb_line_idx, vb_parts, max_right_extent)
    current_svg_start = None
    current_vb_line = None
    current_vb_parts = None
    current_vb_width = None
    max_right = 0

    for i, line in enumerate(lines):
        svg_m = SVG_OPEN.search(line)
        if svg_m:
            vb_str = svg_m.group(2)
            parts = vb_str.split()
            if len(parts) >= 4:
                try:
                    current_vb_width = float(parts[2])
                    current_svg_start = i
                    current_vb_line = i
                    current_vb_parts = parts
                    max_right = 0
                except ValueError:
                    current_vb_width = None

        if current_vb_width is None:
            continue

        # Find text elements
        for m in TEXT_EL.finditer(line):
            attrs = m.group(1)
            content = m.group(2)

            anchor_m = ATTR_ANCHOR.search(attrs)
            anchor = anchor_m.group(1) if anchor_m else "start"

            if anchor != "start":
                continue

            x_m = ATTR_X.search(attrs)
            if not x_m:
                continue
            try:
                x = float(x_m.group(1))
            except ValueError:
                continue

            fs_m = ATTR_FONT_SIZE.search(attrs)
            font_size = float(fs_m.group(1)) if fs_m else 14.0
            is_bold = bool(ATTR_FONT_WEIGHT.search(attrs))

            text_width = estimate_text_width(content, font_size, is_bold)
            right_edge = x + text_width
            if right_edge > max_right:
                max_right = right_edge

        if SVG_CLOSE.search(line):
            if current_vb_width is not None and max_right > current_vb_width:
                svg_blocks.append((current_svg_start, current_vb_line, current_vb_parts, max_right))
            current_vb_width = None

    # Second pass: widen viewBoxes that need it
    for _, vb_line_idx, vb_parts, max_right in svg_blocks:
        old_width = float(vb_parts[2])
        new_width = max_right + PADDING
        # Round up to nearest 10
        new_width = int((new_width + 9) // 10 * 10)
        if new_width <= old_width:
            continue

        vb_parts_new = list(vb_parts)
        vb_parts_new[2] = str(new_width)
        old_vb = " ".join(vb_parts)
        new_vb = " ".join(vb_parts_new)
        lines[vb_line_idx] = lines[vb_line_idx].replace(old_vb, new_vb, 1)
        changed = True
        total_svgs_widened += 1

    if changed:
        f.write_text("\n".join(lines), encoding="utf-8")
        files_fixed += 1

print(f"Widened {total_svgs_widened} SVG viewBoxes in {files_fixed} files")

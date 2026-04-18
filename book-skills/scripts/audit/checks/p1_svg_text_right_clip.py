"""Detect SVG <text> elements positioned near the right viewBox edge that will clip.

When text-anchor is 'start' (default) or absent, text flows rightward from the x position.
If x + estimated_text_width > viewBox_width, the text gets clipped.
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "SVG_TEXT_RIGHT_CLIP"
DESCRIPTION = "SVG text near right edge of viewBox will be clipped"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

SVG_OPEN = re.compile(r'<svg\b[^>]*viewBox\s*=\s*"([^"]+)"', re.IGNORECASE)
SVG_CLOSE = re.compile(r'</svg>', re.IGNORECASE)
TEXT_EL = re.compile(
    r'<text\b([^>]*)>(.*?)</text>',
    re.IGNORECASE | re.DOTALL,
)
ATTR_X = re.compile(r'\bx\s*=\s*"([^"]+)"')
ATTR_ANCHOR = re.compile(r'text-anchor\s*=\s*"([^"]+)"')
ATTR_FONT_SIZE = re.compile(r'font-size\s*=\s*"([^"]+)"')
ATTR_FONT_WEIGHT = re.compile(r'font-weight\s*=\s*"(bold|[6-9]\d\d)"')

# Average character width as fraction of font-size for sans-serif
CHAR_WIDTH_FACTOR = 0.58
BOLD_FACTOR = 1.08


def estimate_text_width(content, font_size, is_bold):
    """Estimate rendered text width in SVG units."""
    # Strip child elements to get visible text
    clean = re.sub(r'<[^>]+>', '', content).strip()
    w = len(clean) * font_size * CHAR_WIDTH_FACTOR
    if is_bold:
        w *= BOLD_FACTOR
    return w


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    current_vb_width = None
    svg_start_line = 0

    for i, line in enumerate(lines, 1):
        # Track SVG open/close
        svg_m = SVG_OPEN.search(line)
        if svg_m:
            parts = svg_m.group(1).split()
            if len(parts) >= 4:
                try:
                    current_vb_width = float(parts[2])
                except ValueError:
                    current_vb_width = None
            svg_start_line = i

        if SVG_CLOSE.search(line):
            current_vb_width = None
            continue

        if current_vb_width is None:
            continue

        # Find text elements on this line
        for m in TEXT_EL.finditer(line):
            attrs = m.group(1)
            content = m.group(2)

            # Get text-anchor
            anchor_m = ATTR_ANCHOR.search(attrs)
            anchor = anchor_m.group(1) if anchor_m else "start"

            # Only check start-anchored text (flows rightward)
            if anchor != "start":
                continue

            # Get x position
            x_m = ATTR_X.search(attrs)
            if not x_m:
                continue
            try:
                x = float(x_m.group(1))
            except ValueError:
                continue

            # Get font size
            fs_m = ATTR_FONT_SIZE.search(attrs)
            font_size = float(fs_m.group(1)) if fs_m else 14.0

            # Check bold
            is_bold = bool(ATTR_FONT_WEIGHT.search(attrs))

            # Estimate width
            text_width = estimate_text_width(content, font_size, is_bold)
            right_edge = x + text_width

            # Flag if text extends beyond viewBox with a margin
            margin = 5  # small tolerance
            if right_edge > current_vb_width + margin:
                overflow = right_edge - current_vb_width
                clean_text = re.sub(r'<[^>]+>', '', content).strip()[:30]
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, i,
                    f'Text "{clean_text}" at x={x} extends ~{overflow:.0f}px beyond viewBox width {current_vb_width:.0f}',
                ))

    return issues

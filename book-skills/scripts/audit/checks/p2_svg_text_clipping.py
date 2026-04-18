"""Detect SVG <text> elements whose coordinates fall outside or near the viewBox boundary."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "SVG_TEXT_CLIPPING"
DESCRIPTION = "SVG text element positioned near or outside viewBox boundary (likely clipped)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match <svg ...viewBox="minX minY width height"...>
VIEWBOX_RE = re.compile(
    r'<svg\b[^>]*\bviewBox=["\']'
    r'\s*(-?[\d.]+)\s+(-?[\d.]+)\s+([\d.]+)\s+([\d.]+)\s*'
    r'["\']',
    re.IGNORECASE
)

# Match <text ...x="N" y="N"...> or <text ...x="N" ...y="N"...>
TEXT_COORD_RE = re.compile(
    r'<text\b[^>]*?\bx=["\'](-?[\d.]+)["\'][^>]*?\by=["\'](-?[\d.]+)["\']',
    re.IGNORECASE
)

# Also match y before x
TEXT_COORD_RE2 = re.compile(
    r'<text\b[^>]*?\by=["\'](-?[\d.]+)["\'][^>]*?\bx=["\'](-?[\d.]+)["\']',
    re.IGNORECASE
)

# Margin: text within this many units of the edge is considered at risk
MARGIN = 15


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    # Track current viewBox as we scan through lines
    current_vb = None  # (minX, minY, width, height)
    svg_depth = 0

    for i, line in enumerate(lines, 1):
        # Track SVG open/close
        if "<svg" in line.lower():
            m = VIEWBOX_RE.search(line)
            if m:
                current_vb = (
                    float(m.group(1)),
                    float(m.group(2)),
                    float(m.group(3)),
                    float(m.group(4))
                )
            svg_depth += 1

        if "</svg>" in line.lower():
            svg_depth -= 1
            if svg_depth <= 0:
                current_vb = None
                svg_depth = 0

        # Check text elements
        if current_vb and "<text" in line.lower():
            vb_x, vb_y, vb_w, vb_h = current_vb
            max_x = vb_x + vb_w
            max_y = vb_y + vb_h

            # Try both coordinate orderings
            m = TEXT_COORD_RE.search(line)
            if m:
                tx, ty = float(m.group(1)), float(m.group(2))
            else:
                m2 = TEXT_COORD_RE2.search(line)
                if m2:
                    ty, tx = float(m2.group(1)), float(m2.group(2))
                else:
                    continue

            clipped = []
            if tx < vb_x + MARGIN:
                clipped.append(f"x={tx} near left edge ({vb_x})")
            if tx > max_x - MARGIN:
                clipped.append(f"x={tx} near right edge ({max_x})")
            if ty < vb_y + MARGIN:
                clipped.append(f"y={ty} near top edge ({vb_y})")
            if ty > max_y - MARGIN:
                clipped.append(f"y={ty} near bottom edge ({max_y})")

            if clipped:
                # Extract text content for context
                text_content = re.sub(r'<[^>]+>', '', line).strip()[:60]
                issues.append(Issue(
                    priority=PRIORITY,
                    check_id=CHECK_ID,
                    filepath=filepath,
                    line=i,
                    message=f"Text \"{text_content}\" may be clipped: {'; '.join(clipped)}"
                ))

    return issues

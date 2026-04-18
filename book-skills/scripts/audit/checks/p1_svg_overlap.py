"""Detect SVG diagrams with overlapping content-panel rect elements.

Finds large <rect> elements (width >= 80px) within the same SVG that share
similar y positions but have overlapping x ranges, indicating side-by-side
content panels that visually overlap and clip text.

Small rects (icons, decorations, shadows) are excluded to reduce noise.
"""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "SVG_OVERLAP"
DESCRIPTION = "SVG contains overlapping content panels"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Minimum rect dimensions to be considered a content panel
MIN_PANEL_WIDTH = 80
MIN_PANEL_HEIGHT = 30
# Minimum overlap in px to flag
MIN_OVERLAP_PX = 15

# Match rect with x, y, width, height in any order using lookaheads
RECT_RE = re.compile(
    r'<rect\s(?=[^>]*x="(?P<x>[\d.]+)")(?=[^>]*y="(?P<y>[\d.]+)")'
    r'(?=[^>]*width="(?P<w>[\d.]+)")(?=[^>]*height="(?P<h>[\d.]+)")[^>]*/?>',
    re.DOTALL,
)

SVG_RE = re.compile(r'<svg\s[^>]*?viewBox="(?P<vb>[^"]+)"[^>]*>.*?</svg>', re.DOTALL)

Y_TOLERANCE = 5  # rects within 5px of same y are considered same row


def _parse_panel_rects(svg_text):
    """Extract large panel rects from SVG text (skip small decorative rects)."""
    rects = []
    for m in RECT_RE.finditer(svg_text):
        w = float(m.group("w"))
        h = float(m.group("h"))
        if w >= MIN_PANEL_WIDTH and h >= MIN_PANEL_HEIGHT:
            rects.append({
                "x": float(m.group("x")),
                "y": float(m.group("y")),
                "w": w,
                "h": h,
            })
    return rects


def _group_by_y(rects):
    """Group rects into rows by similar y coordinate."""
    if not rects:
        return []
    sorted_rects = sorted(rects, key=lambda r: r["y"])
    rows = []
    current_row = [sorted_rects[0]]
    for r in sorted_rects[1:]:
        if abs(r["y"] - current_row[0]["y"]) <= Y_TOLERANCE:
            current_row.append(r)
        else:
            if len(current_row) >= 2:
                rows.append(current_row)
            current_row = [r]
    if len(current_row) >= 2:
        rows.append(current_row)
    return rows


def _check_overlaps(row):
    """Check for x-range overlaps within a row of rects."""
    overlaps = []
    sorted_row = sorted(row, key=lambda r: r["x"])
    for i in range(len(sorted_row) - 1):
        a = sorted_row[i]
        b = sorted_row[i + 1]
        a_right = a["x"] + a["w"]
        if a_right > b["x"] + MIN_OVERLAP_PX:
            overlap_px = a_right - b["x"]
            overlaps.append((a, b, overlap_px))
    return overlaps


def run(filepath, html, context):
    issues = []

    for svg_match in SVG_RE.finditer(html):
        svg_text = svg_match.group(0)
        svg_start = svg_match.start()
        line_num = html[:svg_start].count("\n") + 1

        vb_parts = svg_match.group("vb").split()
        if len(vb_parts) != 4:
            continue
        vb_w = float(vb_parts[2])

        rects = _parse_panel_rects(svg_text)
        if len(rects) < 2:
            continue

        # Check for panel rects exceeding viewBox
        for r in rects:
            if r["x"] + r["w"] > vb_w + 5:
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, line_num,
                    f"SVG panel rect at x={r['x']} w={r['w']} exceeds viewBox width {vb_w}"
                ))

        # Check for overlapping panels in same row
        rows = _group_by_y(rects)
        for row in rows:
            overlaps = _check_overlaps(row)
            for a, b, overlap_px in overlaps:
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, line_num,
                    f"Overlapping panels at y~{a['y']}: "
                    f"[x={a['x']},w={a['w']}] and [x={b['x']},w={b['w']}] "
                    f"overlap by {overlap_px:.0f}px"
                ))

    return issues

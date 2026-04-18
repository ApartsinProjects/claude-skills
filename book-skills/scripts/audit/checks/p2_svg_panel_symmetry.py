"""Check for asymmetric panels in SVG diagrams (left/right or multi-column layouts)."""
import re
from collections import namedtuple, defaultdict

PRIORITY = "P2"
CHECK_ID = "SVG_PANEL_ASYM"
DESCRIPTION = "SVG diagram has asymmetric panel sizes (left/right or columns)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

SVG_BLOCK_RE = re.compile(r'(<svg\b[^>]*>)(.*?)(</svg>)', re.DOTALL | re.IGNORECASE)
RECT_RE = re.compile(r'<rect\b([^>]*)/?>')
WIDTH_RE = re.compile(r'\bwidth=["\'](\d+(?:\.\d+)?)["\']')
HEIGHT_RE = re.compile(r'\bheight=["\'](\d+(?:\.\d+)?)["\']')
X_RE = re.compile(r'\bx=["\'](\d+(?:\.\d+)?)["\']')
Y_RE = re.compile(r'\by=["\'](\d+(?:\.\d+)?)["\']')
RX_RE = re.compile(r'\brx=["\'](\d+(?:\.\d+)?)["\']')

# Panel detection: large rects that serve as backgrounds/containers
MIN_PANEL_WIDTH = 80
MIN_PANEL_HEIGHT = 60


def _extract_rects(svg_body):
    """Extract rectangle dimensions from SVG body."""
    rects = []
    for m in RECT_RE.finditer(svg_body):
        attrs = m.group(1)
        w_m = WIDTH_RE.search(attrs)
        h_m = HEIGHT_RE.search(attrs)
        x_m = X_RE.search(attrs)
        y_m = Y_RE.search(attrs)
        if w_m and h_m:
            w = float(w_m.group(1))
            h = float(h_m.group(1))
            x = float(x_m.group(1)) if x_m else 0
            y = float(y_m.group(1)) if y_m else 0
            if w >= MIN_PANEL_WIDTH and h >= MIN_PANEL_HEIGHT:
                rects.append({"x": x, "y": y, "w": w, "h": h})
    return rects


def _find_panel_groups(rects):
    """Find groups of rects at similar y positions (horizontal panels)."""
    if len(rects) < 2:
        return []

    # Group by similar y position (within 10px)
    groups = defaultdict(list)
    for r in rects:
        bucket = round(r["y"] / 15) * 15  # 15px buckets
        groups[bucket].append(r)

    # Return groups with 2+ panels
    return [g for g in groups.values() if len(g) >= 2]


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    for m in SVG_BLOCK_RE.finditer(html):
        svg_tag = m.group(1)
        svg_body = m.group(2)
        svg_start = html[:m.start()].count("\n") + 1

        rects = _extract_rects(svg_body)
        if not rects:
            continue

        panel_groups = _find_panel_groups(rects)
        for group in panel_groups:
            widths = sorted([r["w"] for r in group])
            if len(widths) >= 2:
                min_w = widths[0]
                max_w = widths[-1]
                # Flag if width ratio exceeds 1.3 (30% difference)
                if min_w > 0 and max_w / min_w > 1.3:
                    heights = [r["h"] for r in group]
                    h_min = min(heights)
                    h_max = max(heights)
                    size_str = " vs ".join(f"{r['w']:.0f}x{r['h']:.0f}" for r in sorted(group, key=lambda r: r["x"]))
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, svg_start,
                        f"Asymmetric panels at y~{group[0]['y']:.0f}: {size_str} "
                        f"(ratio {max_w/min_w:.2f}x)"))

    return issues

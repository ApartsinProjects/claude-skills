"""Check for text in SVG shapes that overflows the shape boundaries."""
import re
import html as html_mod
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "SVG_TEXT_OVERFLOW"
DESCRIPTION = "SVG text likely overflows its containing shape"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

CIRCLE_RE = re.compile(r'<circle\b[^>]*?cx=["\']([^"\']+)["\'][^>]*?cy=["\']([^"\']+)["\'][^>]*?r=["\']([^"\']+)["\']')
TEXT_RE = re.compile(r'<text\b([^>]*)>([^<]+)</text>')
X_RE = re.compile(r'\bx=["\']([^"\']+)["\']')
Y_RE = re.compile(r'\by=["\']([^"\']+)["\']')
FSIZE_RE = re.compile(r'\bfont-size=["\']([^"\']+)["\']')
FONT_RE = re.compile(r'\bfont-family=["\']([^"\']+)["\']')

# Width factor per character (monospace vs proportional)
MONO_FONTS = {"consolas", "courier", "monospace", "source code pro", "fira code"}


def _estimate_width(text, font_size, font_family):
    """Estimate rendered text width in pixels."""
    decoded = html_mod.unescape(text.strip())
    char_count = len(decoded)
    is_mono = any(f in font_family.lower() for f in MONO_FONTS) if font_family else False
    factor = 0.62 if is_mono else 0.55
    return char_count * font_size * factor


def _is_inside_svg(html_text, line_num, lines):
    """Quick check if line is inside an SVG block."""
    svg_depth = 0
    for j in range(line_num - 1):
        l = lines[j]
        svg_depth += l.count("<svg") - l.count("</svg>")
    return svg_depth > 0


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    # Collect all circles with their positions (as simple lookup)
    circles = []  # (cx, cy, r, line_num)
    for i, line in enumerate(lines, 1):
        for m in CIRCLE_RE.finditer(line):
            try:
                cx, cy, r = float(m.group(1)), float(m.group(2)), float(m.group(3))
                circles.append((cx, cy, r, i))
            except ValueError:
                continue

    if not circles:
        return issues

    # Check each text element
    for i, line in enumerate(lines, 1):
        for m in TEXT_RE.finditer(line):
            attrs = m.group(1)
            text_content = m.group(2).strip()

            x_match = X_RE.search(attrs)
            y_match = Y_RE.search(attrs)
            fsize_match = FSIZE_RE.search(attrs)
            font_match = FONT_RE.search(attrs)

            if not x_match or not y_match or not fsize_match:
                continue

            try:
                tx = float(x_match.group(1))
                ty = float(y_match.group(1))
                fsize = float(fsize_match.group(1))
            except ValueError:
                continue

            font_family = font_match.group(1) if font_match else ""
            est_width = _estimate_width(text_content, fsize, font_family)

            # Find nearest circle (within 5px of center)
            for cx, cy, r, _ in circles:
                dist = ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5
                if dist < r + 5:
                    diameter = 2 * r
                    if est_width > diameter * 0.95:  # 5% tolerance
                        overflow_pct = int((est_width / diameter - 1) * 100)
                        decoded = html_mod.unescape(text_content)[:30]
                        issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                            f'Text "{decoded}" overflows circle (r={r:.0f}): '
                            f'est {est_width:.0f}px vs {diameter:.0f}px diameter '
                            f'(+{overflow_pct}%)'))
                    break

    return issues

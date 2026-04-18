"""Check for redundant title text inside SVG diagrams (duplicates the caption below)."""
import re
from collections import namedtuple

PRIORITY = "P0"
CHECK_ID = "SVG_TITLE_TEXT"
DESCRIPTION = "SVG contains a title-like <text> element that duplicates the external caption"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match <text ... y="N" ... font-size="N" ... font-weight="bold" ...>long text</text>
TEXT_RE = re.compile(
    r'<text\b([^>]*)>([^<]{10,})</text>', re.IGNORECASE
)
Y_RE = re.compile(r'\by=["\'](\d+(?:\.\d+)?)["\']')
FSIZE_RE = re.compile(r'\bfont-size=["\'](\d+(?:\.\d+)?)["\']')
BOLD_RE = re.compile(r'\bfont-weight=["\'](?:bold|[67]00)["\']')


def _is_inside_svg(html, pos):
    """Check if position is inside an <svg> block."""
    before = html[:pos]
    last_open = before.rfind("<svg")
    last_close = before.rfind("</svg>")
    return last_open > last_close


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    for i, line_text in enumerate(lines, 1):
        for m in TEXT_RE.finditer(line_text):
            attrs = m.group(1)
            text_content = m.group(2).strip()

            # Must be bold or large font
            y_match = Y_RE.search(attrs)
            fsize_match = FSIZE_RE.search(attrs)
            is_bold = bool(BOLD_RE.search(attrs))

            if not y_match or not fsize_match:
                continue

            y_val = float(y_match.group(1))
            fsize_val = float(fsize_match.group(1))

            # Title criteria: near top (y <= 45), large font (>= 13), bold
            if y_val <= 45 and fsize_val >= 13 and is_bold:
                # Check word count (titles have 3+ words)
                words = text_content.split()
                if len(words) >= 3:
                    # Verify inside SVG
                    line_start = sum(len(lines[j]) + 1 for j in range(i - 1))
                    if _is_inside_svg(html, line_start):
                        display = text_content[:60]
                        issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                            f'SVG title text (redundant with caption): "{display}"'))
    return issues

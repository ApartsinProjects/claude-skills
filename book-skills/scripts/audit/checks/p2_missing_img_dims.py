"""Check for <img> tags missing width or height attributes (causes layout shift)."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "MISSING_IMG_DIMS"
DESCRIPTION = "<img> tag missing width or height attributes"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

IMG_RE = re.compile(r'<img\b([^>]*)/?>', re.IGNORECASE)
SRC_RE = re.compile(r'src=["\']([^"\']+)["\']')


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in IMG_RE.finditer(line):
            attrs = m.group(1)
            has_width = "width=" in attrs
            has_height = "height=" in attrs
            if not has_width or not has_height:
                src_m = SRC_RE.search(attrs)
                src = src_m.group(1)[:50] if src_m else "(unknown)"
                missing = []
                if not has_width:
                    missing.append("width")
                if not has_height:
                    missing.append("height")
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'<img src="{src}"> missing {", ".join(missing)}'))
    return issues

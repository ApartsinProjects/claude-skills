"""Check for heading level skips (e.g. h1 followed by h3, h2 followed by h4)."""
import re
import os
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "HEADING_HIERARCHY"
DESCRIPTION = "Heading level skip detected (e.g. h1 to h3)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

HEADING_RE = re.compile(r'<(h[1-6])\b[^>]*>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r'<[^>]+>')


def run(filepath, html, context):
    # Only check section files
    basename = os.path.basename(filepath)
    if "section-" not in basename:
        return []

    issues = []
    prev_level = 0
    for i, line in enumerate(html.split("\n"), 1):
        for m in HEADING_RE.finditer(line):
            tag = m.group(1).lower()
            level = int(tag[1])
            text = TAG_RE.sub('', m.group(2)).strip()
            if prev_level > 0 and level > prev_level + 1:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'Heading skip: h{prev_level} to h{level} ("{text}")'))
            prev_level = level
    return issues

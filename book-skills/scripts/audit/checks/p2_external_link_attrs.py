"""Check that external links have target="_blank" and rel="noopener"."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "EXT_LINK_ATTRS"
DESCRIPTION = "External link missing target=\"_blank\" or rel=\"noopener\""

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

LINK_RE = re.compile(r'<a\b([^>]*)>', re.IGNORECASE)
HREF_RE = re.compile(r'href=["\']((https?://)[^"\']*)["\']', re.IGNORECASE)
TARGET_RE = re.compile(r'target=["\']_blank["\']', re.IGNORECASE)
REL_NOOPENER_RE = re.compile(r'rel=["\'][^"\']*noopener[^"\']*["\']', re.IGNORECASE)
NAV_OPEN = re.compile(r'<nav[\s>]', re.IGNORECASE)
NAV_CLOSE = re.compile(r'</nav>', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    nav_depth = 0
    for i, line in enumerate(html.split("\n"), 1):
        # Track nav nesting (simple depth counter)
        nav_depth += len(NAV_OPEN.findall(line))
        nav_depth -= len(NAV_CLOSE.findall(line))
        if nav_depth < 0:
            nav_depth = 0
        if nav_depth > 0:
            continue
        for m in LINK_RE.finditer(line):
            attrs = m.group(1)
            href_m = HREF_RE.search(attrs)
            if not href_m:
                continue
            url = href_m.group(1)
            missing = []
            if not TARGET_RE.search(attrs):
                missing.append('target="_blank"')
            if not REL_NOOPENER_RE.search(attrs):
                missing.append('rel="noopener"')
            if missing:
                short_url = url[:60] + "..." if len(url) > 60 else url
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'External link <a href="{short_url}"> missing {", ".join(missing)}'))
    return issues

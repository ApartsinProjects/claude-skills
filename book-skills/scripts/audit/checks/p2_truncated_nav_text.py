"""Check for navigation link text that ends with ellipsis (truncated labels)."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "TRUNCATED_NAV"
DESCRIPTION = "Navigation link text appears truncated (ends with ellipsis)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

NAV_OPEN = re.compile(r'<nav[\s>]', re.IGNORECASE)
NAV_CLOSE = re.compile(r'</nav>', re.IGNORECASE)
CHAPTER_NAV_OPEN = re.compile(r'class=["\'][^"\']*chapter-nav[^"\']*["\']', re.IGNORECASE)
DIV_OPEN = re.compile(r'<div\b[^>]*>', re.IGNORECASE)
DIV_CLOSE = re.compile(r'</div>', re.IGNORECASE)
LINK_RE = re.compile(r'<a\b[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r'<[^>]+>')
ELLIPSIS_RE = re.compile(r'(?:\.\.\.|' + '\u2026' + r')\s*$')


def run(filepath, html, context):
    issues = []
    in_nav = False
    nav_depth = 0
    for i, line in enumerate(html.split("\n"), 1):
        # Track <nav> regions
        if NAV_OPEN.search(line) or CHAPTER_NAV_OPEN.search(line):
            in_nav = True
            nav_depth += 1
        if NAV_CLOSE.search(line) or (in_nav and DIV_CLOSE.search(line) and CHAPTER_NAV_OPEN.search(html)):
            # Simplified: decrement when closing nav
            for _ in NAV_CLOSE.findall(line):
                nav_depth -= 1
                if nav_depth <= 0:
                    in_nav = False
                    nav_depth = 0
        if not in_nav:
            continue
        for m in LINK_RE.finditer(line):
            text = TAG_RE.sub('', m.group(1)).strip()
            if ELLIPSIS_RE.search(text):
                short_text = text[:50] + "..." if len(text) > 50 else text
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'Truncated nav text: "{short_text}"'))
    return issues

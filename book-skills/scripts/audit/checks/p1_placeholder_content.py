"""Check for placeholder or pending content in published HTML files."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "PLACEHOLDER_CONTENT"
DESCRIPTION = "Placeholder or pending content detected in published page"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Patterns that indicate genuine placeholder content needing replacement.
# The \bplaceholder\b pattern is intentionally omitted from the general list
# because it produces too many false positives in educational prose that
# discusses placeholders as a concept. Instead, we use targeted patterns that
# catch actual placeholder content (e.g., "[PLACEHOLDER]", "placeholder text").
PLACEHOLDER_PATTERNS = [
    re.compile(r'\bContent\s+pending\b', re.IGNORECASE),
    re.compile(r'\bTODO\b'),
    re.compile(r'\bFIXME\b'),
    re.compile(r'\bTBD\b'),
    re.compile(r'\bwill be produced\b', re.IGNORECASE),
    re.compile(r'\bwill be generated\b', re.IGNORECASE),
    re.compile(r'\bcoming soon\b', re.IGNORECASE),
    # Only flag "placeholder" when it looks like actual placeholder content,
    # not when used as a descriptive word in educational prose.
    re.compile(r'\[placeholder\]', re.IGNORECASE),
    re.compile(r'\bPLACEHOLDER\b'),  # ALL-CAPS only
    re.compile(r'\bplaceholder\s+text\b', re.IGNORECASE),
    re.compile(r'\binsert\s+.*\bhere\b', re.IGNORECASE),
    re.compile(r'\bLorem\s+ipsum\b', re.IGNORECASE),
]

COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
MAIN_OPEN = re.compile(r'<main[\s>]', re.IGNORECASE)
MAIN_CLOSE = re.compile(r'</main>', re.IGNORECASE)

# Regex to strip content inside <pre>, <code>, and <samp> tags.
# Uses DOTALL so multi-line <pre> blocks are handled correctly.
CODE_BLOCK_TAGS = re.compile(
    r'<(pre|code|samp)\b[^>]*>.*?</\1>',
    re.IGNORECASE | re.DOTALL,
)

# Strip code-caption divs that describe code examples (may reference TODO
# comments or placeholder variables from the code they accompany).
CODE_CAPTION_RE = re.compile(
    r'<div\s+class="code-caption"[^>]*>.*?</div>',
    re.IGNORECASE | re.DOTALL,
)

# Strip HTML placeholder attributes, e.g. placeholder="Enter text...".
PLACEHOLDER_ATTR_RE = re.compile(
    r'\bplaceholder\s*=\s*["\'][^"\']*["\']',
    re.IGNORECASE,
)


def _strip_excluded_regions(html):
    """Remove regions that should not be scanned for placeholders."""
    html = CODE_BLOCK_TAGS.sub('', html)
    html = CODE_CAPTION_RE.sub('', html)
    html = PLACEHOLDER_ATTR_RE.sub('', html)
    return html


def run(filepath, html, context):
    issues = []
    # Strip HTML comments to avoid false positives
    cleaned = COMMENT_RE.sub('', html)
    # Strip code example regions and other excluded zones so that intentional
    # TODO/FIXME/placeholder references in code samples are not flagged.
    cleaned = _strip_excluded_regions(cleaned)

    lines = cleaned.split("\n")
    in_main = False
    for i, line in enumerate(lines, 1):
        if MAIN_OPEN.search(line):
            in_main = True
        if MAIN_CLOSE.search(line):
            in_main = False
            continue
        if not in_main:
            continue
        for pat in PLACEHOLDER_PATTERNS:
            m = pat.search(line)
            if m:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'Placeholder content found: "{m.group()}"'))
                break
    return issues

"""Check for KaTeX or Prism loaded on pages that do not use them."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "UNUSED_VENDOR"
DESCRIPTION = "KaTeX or Prism JS/CSS loaded but not used on this page"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

KATEX_LOAD = re.compile(r'(?:href|src)="[^"]*katex[^"]*"', re.IGNORECASE)
PRISM_LOAD = re.compile(r'(?:href|src)="[^"]*prism[^"]*"', re.IGNORECASE)

# Strip script/style blocks before checking for math delimiters
STRIP_RE = re.compile(r'<(?:script|style)[^>]*>.*?</(?:script|style)>', re.DOTALL | re.IGNORECASE)


def run(filepath, html, context):
    issues = []

    loads_katex = bool(KATEX_LOAD.search(html))
    loads_prism = bool(PRISM_LOAD.search(html))

    if not loads_katex and not loads_prism:
        return issues

    # Strip script/style for content analysis
    body_match = re.search(r'<body[^>]*>(.*)</body>', html, re.DOTALL | re.IGNORECASE)
    if not body_match:
        return issues
    body = STRIP_RE.sub('', body_match.group(1))

    if loads_katex:
        has_math = bool(re.search(r'\$\$', body)) or bool(re.search(r'\$[^$\s][^$]*\$', body))
        if not has_math:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, 1,
                "KaTeX loaded but no math expressions found"))

    if loads_prism:
        has_code = bool(re.search(r'<pre\b', body, re.IGNORECASE))
        if not has_code:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, 1,
                "Prism loaded but no code blocks found"))

    return issues

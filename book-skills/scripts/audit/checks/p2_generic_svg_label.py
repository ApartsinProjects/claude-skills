"""Check SVG aria-label attributes for generic, non-descriptive values."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "GENERIC_SVG_LABEL"
DESCRIPTION = "SVG aria-label is generic and does not describe the content"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

SVG_ARIA_RE = re.compile(
    r'<svg\b[^>]*\baria-label=["\']([^"\']*)["\']',
    re.IGNORECASE
)

# Patterns that indicate a generic, non-descriptive label
GENERIC_PATTERNS = [
    re.compile(r'^(?:Diagram|Figure|Chart|Image|SVG|Graphic|Illustration)\s*$', re.IGNORECASE),
    re.compile(r'^(?:Diagram|Figure|Chart|Image)\s+\d+', re.IGNORECASE),
    re.compile(r'^(?:Diagram|Figure|Chart|Image)\s+[A-Z]?\d*\.?\d+', re.IGNORECASE),
    re.compile(r'^(?:img|pic|svg)\d*$', re.IGNORECASE),
    re.compile(r'^$'),  # empty label
]


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in SVG_ARIA_RE.finditer(line):
            label = m.group(1).strip()
            for pattern in GENERIC_PATTERNS:
                if pattern.match(label):
                    display = label if label else "(empty)"
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                        f'Generic SVG aria-label: "{display}"'))
                    break
    return issues

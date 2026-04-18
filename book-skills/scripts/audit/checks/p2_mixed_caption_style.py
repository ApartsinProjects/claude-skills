"""Flag files that mix different caption element styles for figures/diagrams."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "MIXED_CAPTION_STYLE"
DESCRIPTION = "File uses multiple caption styles (figcaption vs div.diagram-caption vs div.code-caption)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

PATTERNS = [
    ("figcaption", re.compile(r"<figcaption\b", re.IGNORECASE)),
    ("div.diagram-caption", re.compile(r'<div\s+class="diagram-caption"', re.IGNORECASE)),
    ("div.code-caption", re.compile(r'<div\s+class="code-caption"', re.IGNORECASE)),
]


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    # Collect which styles are used and their first occurrence line
    found_styles = {}
    for i, line in enumerate(lines, 1):
        for name, pattern in PATTERNS:
            if name not in found_styles and pattern.search(line):
                found_styles[name] = i

    # Only flag if more than one style is used in the same file
    if len(found_styles) > 1:
        styles_desc = ", ".join(
            f"{name} (line {ln})" for name, ln in sorted(found_styles.items(), key=lambda x: x[1])
        )
        # Report on the second style found (that's the inconsistency)
        sorted_styles = sorted(found_styles.items(), key=lambda x: x[1])
        for name, ln in sorted_styles[1:]:
            issues.append(Issue(
                priority=PRIORITY,
                check_id=CHECK_ID,
                filepath=filepath,
                line=ln,
                message=f"Mixed caption styles in file: {styles_desc}",
            ))

    return issues

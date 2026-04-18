"""
Detect $$...$$ blocks that still contain \\textbf{} with non-LaTeX prose.

This catches the problematic pattern where titles and descriptions sit
inside display math blocks, causing KaTeX to render English text in
math-italic font.
"""

import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "MATH_PROSE_MIXING"
DESCRIPTION = "Display math block ($$) mixes prose titles/text with formulas"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])


def run(filepath, html, context):
    """Return findings for one file."""
    if "section-" not in filepath.name:
        return []

    issues = []

    for m in re.finditer(r"\$\$(.*?)\$\$", html, re.DOTALL):
        block = m.group(1)

        # Only flag blocks containing \textbf{ (the title-in-math pattern)
        if "\\textbf{" not in block:
            continue

        # Count English words outside LaTeX commands
        remaining = re.sub(r"\\textbf\{[^}]*\}", "", block)
        remaining = re.sub(r"\\text\{[^}]*\}", "", remaining)
        remaining = re.sub(r"\\[a-zA-Z]+", "", remaining)
        remaining = re.sub(r"[_^{}()|/\[\].,;:=+*<>\\0-9\-]", " ", remaining)
        remaining = re.sub(r"&[A-Za-z#0-9x]+;", " ", remaining)
        words = [w for w in remaining.split() if len(w) >= 3 and w.isalpha()]

        # If there are substantial prose words alongside \textbf{}, flag it
        if len(words) >= 3:
            line_num = html[:m.start()].count("\n") + 1
            snippet = block.strip()[:80].replace("\n", " ")
            issues.append(Issue(
                priority=PRIORITY,
                check_id=CHECK_ID,
                filepath=filepath,
                line=line_num,
                message=(
                    "$$...$$ block contains \\textbf{} with "
                    + str(len(words))
                    + " prose words: "
                    + snippet
                ),
            ))

    return issues

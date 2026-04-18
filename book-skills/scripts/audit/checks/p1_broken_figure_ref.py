"""Flag prose references to Figure/Code Fragment numbers that have no matching caption."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "BROKEN_FIGURE_REF"
DESCRIPTION = "Prose references a Figure or Code Fragment number with no matching caption in the file"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Matches "Figure X.Y.Z" or "Code Fragment X.Y.Z" in prose (not inside tags)
PROSE_REF_RE = re.compile(
    r"(?:Figure|Code Fragment)\s+(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE
)

# Multiple caption formats used in the book:
# 1. <strong>Figure 26.1.1</strong>  or  <strong>Code Fragment 9.1.2:</strong>
# 2. # Code Fragment 31.8.1: ... (comment inside code block)
# 3. <div class="code-caption"><strong>Code Fragment ...
CAPTION_PATTERNS = [
    re.compile(
        r"<strong>\s*(?:Figure|Code Fragment)\s+(\d+\.\d+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"#\s*(?:Figure|Code Fragment)\s+(\d+\.\d+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
]


def _strip_tags(text):
    """Remove HTML tags to get prose-only text."""
    return re.sub(r"<[^>]+>", " ", text)


def _is_inside_code_block(lines, line_idx):
    """Check if a line is inside a <pre><code> block."""
    depth = 0
    for j in range(line_idx):
        if re.search(r"<pre>|<code\b", lines[j], re.IGNORECASE):
            depth += 1
        if re.search(r"</code>|</pre>", lines[j], re.IGNORECASE):
            depth = max(0, depth - 1)
    return depth > 0


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    # Step 1: collect all caption-defined figure/code-fragment numbers
    defined = set()
    for line in lines:
        for pattern in CAPTION_PATTERNS:
            for m in pattern.finditer(line):
                defined.add(m.group(1))

    # Step 2: scan prose for references (skip captions and code blocks)
    in_code = False
    for i, line in enumerate(lines, 1):
        # Track code blocks
        if re.search(r"<pre\b|<code\b", line, re.IGNORECASE):
            in_code = True
        if re.search(r"</code>|</pre>", line, re.IGNORECASE):
            in_code = False
            continue

        # Skip lines inside code blocks
        if in_code:
            continue

        # Skip lines that ARE captions
        is_caption = False
        for pattern in CAPTION_PATTERNS:
            if pattern.search(line):
                is_caption = True
                break
        if is_caption:
            continue

        # Check prose text for figure/code-fragment references
        prose = _strip_tags(line)
        for m in PROSE_REF_RE.finditer(prose):
            ref_num = m.group(1)
            if ref_num not in defined:
                label = m.group(0)
                issues.append(Issue(
                    priority=PRIORITY,
                    check_id=CHECK_ID,
                    filepath=filepath,
                    line=i,
                    message=f"'{label}' referenced in prose but no caption defines it",
                ))

    return issues

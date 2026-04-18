"""Check for inline style attributes inside code blocks (should use Prism syntax highlighting)."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "INLINE_STYLE_IN_CODE"
DESCRIPTION = "Inline style attribute found inside <pre><code> block (use Prism classes instead)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

INLINE_STYLE_RE = re.compile(r'<span\s+style="color:\s*#[0-9a-fA-F]+', re.IGNORECASE)
CODE_OPEN_RE = re.compile(r'<pre\b[^>]*>\s*<code\b|<code\b[^>]*>\s*<pre\b', re.IGNORECASE)
CODE_CLOSE_RE = re.compile(r'</code>\s*</pre>|</pre>\s*</code>', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    in_code = False
    count = 0
    first_line = 0

    for i, line in enumerate(lines, 1):
        if CODE_OPEN_RE.search(line):
            in_code = True
        if CODE_CLOSE_RE.search(line):
            in_code = False
            continue

        if in_code and INLINE_STYLE_RE.search(line):
            count += 1
            if first_line == 0:
                first_line = i

    if count > 0:
        issues.append(Issue(
            PRIORITY, CHECK_ID, filepath, first_line,
            f'File has {count} inline color styles in code blocks (first at line {first_line}); use Prism classes instead',
        ))

    return issues

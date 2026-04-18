"""Check for headings followed directly by code blocks with no explanatory prose."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "BARE_CODE_AFTER_HEADING"
DESCRIPTION = "Heading followed by <pre><code> with no explanatory paragraph between them"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

HEADING_RE = re.compile(r'<h([23])[^>]*>(.*?)</h\1>', re.DOTALL)
PRE_RE = re.compile(r'<pre\b')
CONTENT_RE = re.compile(r'<(?:p|div|ul|ol|figure|blockquote|table)\b')


def run(filepath, html, context):
    if "section-" not in filepath.name and "appendix" not in str(filepath).lower():
        return []

    issues = []
    lines = html.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]
        h_match = HEADING_RE.search(line)
        if h_match:
            heading_text = re.sub(r'<[^>]+>', '', h_match.group(2)).strip()
            heading_line = i + 1

            # Look ahead: skip blank lines, check if next content element is <pre>
            j = i + 1
            found_content = False
            while j < len(lines) and j < i + 8:  # look up to 8 lines ahead
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                if PRE_RE.search(next_line):
                    # Code block immediately after heading
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, heading_line,
                        f'"{heading_text[:50]}" jumps to code with no intro paragraph'))
                    found_content = True
                    break
                elif CONTENT_RE.search(next_line):
                    # Some other content element (good)
                    found_content = True
                    break
                else:
                    # Could be a code-caption or other inline element
                    if '<div class="code-caption">' in next_line:
                        # Code caption partially mitigates but still no prose
                        found_content = True
                        break
                    j += 1

        i += 1

    return issues

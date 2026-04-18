"""Check for unescaped ampersands in <title> tags."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "UNESCAPED_AMPERSAND_TITLE"
DESCRIPTION = "Unescaped & in <title> tag (should be &amp;)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.IGNORECASE)
# Match bare & that is NOT already part of a character reference (&amp; &#123; &#x1F; etc.)
BARE_AMP = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)")


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        m = TITLE_RE.search(line)
        if m:
            title_text = m.group(1)
            if BARE_AMP.search(title_text):
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, i,
                    f'Unescaped & in <title>: "{title_text.strip()[:70]}"',
                ))
            break  # Only one <title> per file
    return issues

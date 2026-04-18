"""Check for consecutive headings with no intervening content."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "CONSECUTIVE_HEADINGS"
DESCRIPTION = "Two consecutive headings with no content between them"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match any heading tag (h1 through h6)
HEADING_RE = re.compile(r'<(h[1-6])\b[^>]*>(.*?)</\1>', re.DOTALL | re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    headings = list(HEADING_RE.finditer(html))

    for idx in range(len(headings) - 1):
        current = headings[idx]
        nxt = headings[idx + 1]

        # Get the text between end of current heading and start of next
        between = html[current.end():nxt.start()]

        # Strip HTML tags and whitespace to see if there is real content
        text_between = re.sub(r'<[^>]+>', '', between).strip()

        if not text_between:
            cur_tag = current.group(1).lower()
            nxt_tag = nxt.group(1).lower()
            cur_text = re.sub(r'<[^>]+>', '', current.group(2)).strip()[:50]
            nxt_text = re.sub(r'<[^>]+>', '', nxt.group(2)).strip()[:50]
            line_num = html[:nxt.start()].count("\n") + 1
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                f'<{nxt_tag}> "{nxt_text}" follows <{cur_tag}> "{cur_text}" '
                f'with no content between them'))

    return issues

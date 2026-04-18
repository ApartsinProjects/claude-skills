"""Check that <title> tags follow a consistent format with book name suffix."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "TITLE_FORMAT"
DESCRIPTION = "Page <title> does not follow the standard format"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TITLE_RE = re.compile(r'<title>([^<]*)</title>', re.IGNORECASE)
BOOK_SUFFIX = "Building Conversational AI with LLMs and Agents"


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        m = TITLE_RE.search(line)
        if m:
            title = m.group(1).strip()
            if not title:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    "Empty <title> tag"))
            elif "using" in title.lower() and "llm" in title.lower():
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'Title uses "using" instead of "with": "{title[:60]}"'))
            # Check for singular "LLM" without "s"
            if re.search(r'\bLLM\b(?!s)', title) and "LLMs" not in title:
                if "Section" not in title and "Module" not in title:
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                        f'Title uses singular "LLM" instead of "LLMs": "{title[:60]}"'))
            break  # Only check first title
    return issues

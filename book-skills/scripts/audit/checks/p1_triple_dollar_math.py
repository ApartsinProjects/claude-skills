"""Check for malformed triple-dollar math delimiters ($$$)."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "TRIPLE_DOLLAR_MATH"
DESCRIPTION = "Malformed $$$ math delimiter (likely missing line break between display math and inline math)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TRIPLE_DOLLAR = re.compile(r"\$\$\$")


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in TRIPLE_DOLLAR.finditer(line):
            # Extract a small context window around the match
            start = max(0, m.start() - 20)
            end = min(len(line), m.end() + 30)
            snippet = line[start:end].strip()
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, i,
                f'Triple $$$ found (malformed math delimiter): "...{snippet}..."',
            ))
    return issues

"""Check for <th> elements missing scope attribute (accessibility)."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "MISSING_TH_SCOPE"
DESCRIPTION = "<th> element missing scope attribute for accessibility"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TH_RE = re.compile(r'<th\b([^>]*)>')


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in TH_RE.finditer(line):
            attrs = m.group(1)
            if "scope=" not in attrs:
                # Get content preview
                end = line.find("</th>", m.end())
                content = line[m.end():end][:40] if end > 0 else ""
                content = re.sub(r'<[^>]+>', '', content).strip()
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'<th> missing scope: "{content}"'))
    return issues

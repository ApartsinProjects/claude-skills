"""Check for broken cross-reference links (relative hrefs to nonexistent files)."""
import re
from pathlib import Path
from collections import namedtuple

PRIORITY = "P0"
CHECK_ID = "BROKEN_XREF"
DESCRIPTION = "Relative href points to a file that does not exist on disk"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

HREF_RE = re.compile(r'href="([^"]+)"')
SKIP_PREFIXES = ("http://", "https://", "mailto:", "javascript:", "tel:", "#")


def run(filepath, html, context):
    issues = []
    all_files = context["all_files"]
    for i, line in enumerate(html.split("\n"), 1):
        for m in HREF_RE.finditer(line):
            href = m.group(1)
            if any(href.startswith(p) for p in SKIP_PREFIXES):
                continue
            # Strip fragment
            clean = href.split("#")[0]
            if not clean:
                continue
            # Resolve relative path
            target = (filepath.parent / clean).resolve()
            if target not in all_files and not target.exists():
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                    f'Broken link: href="{href}"'))
    return issues

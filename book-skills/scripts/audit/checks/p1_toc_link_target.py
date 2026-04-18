"""Flag pages where the header TOC link points to index.html instead of toc.html."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "TOC_LINK_TARGET"
DESCRIPTION = "Header TOC link should point to toc.html, not index.html"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match the TOC link in header nav: <a href="..." class="toc-link"
TOC_LINK_RE = re.compile(
    r'<a\s+href="([^"]+)"\s+class="toc-link"', re.IGNORECASE
)


def run(filepath, html, context):
    issues = []
    # Skip toc.html and index.html themselves
    fname = filepath.name.lower()
    if fname in ("toc.html", "index.html"):
        return issues

    for i, line in enumerate(html.split("\n"), 1):
        m = TOC_LINK_RE.search(line)
        if m:
            href = m.group(1)
            # The href should end with toc.html, not index.html
            clean = href.split("#")[0].split("?")[0]
            if clean.endswith("index.html"):
                issues.append(Issue(
                    priority=PRIORITY,
                    check_id=CHECK_ID,
                    filepath=filepath,
                    line=i,
                    message=f'TOC link points to "{href}" instead of toc.html',
                ))
    return issues

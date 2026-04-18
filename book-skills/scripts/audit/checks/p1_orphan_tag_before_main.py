"""Flag stray closing tags between </header> and <main>."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "ORPHAN_TAG_BEFORE_MAIN"
DESCRIPTION = "Stray closing tag found between </header> and <main>"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

HEADER_CLOSE_RE = re.compile(r"</header>", re.IGNORECASE)
MAIN_OPEN_RE = re.compile(r"<main\b", re.IGNORECASE)
STRAY_TAG_RE = re.compile(r"^\s*</\w+>\s*$")


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    total = len(lines)

    # Find </header> line
    header_close = None
    main_open = None
    for i, line in enumerate(lines):
        if header_close is None and HEADER_CLOSE_RE.search(line):
            header_close = i
        if header_close is not None and MAIN_OPEN_RE.search(line):
            main_open = i
            break

    if header_close is None or main_open is None:
        return issues

    # Check lines between </header> and <main> for stray tags
    for i in range(header_close + 1, main_open):
        line = lines[i].strip()
        if not line:
            continue
        # Allow blank lines and comments
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        # Flag stray closing tags like </div>
        if STRAY_TAG_RE.match(lines[i]):
            issues.append(Issue(
                priority=PRIORITY,
                check_id=CHECK_ID,
                filepath=filepath,
                line=i + 1,
                message=f"Stray '{line}' found between </header> and <main>",
            ))

    return issues

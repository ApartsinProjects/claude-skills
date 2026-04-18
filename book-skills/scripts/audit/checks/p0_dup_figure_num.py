"""Check for duplicate figure, table, or listing numbers within a single file.

Only counts *caption-bearing* elements (figcaption, code-caption,
diagram-caption, table caption).  Prose cross-references and aria-labels
are expected to repeat the same number and are therefore excluded.
"""
import re
from collections import defaultdict, namedtuple

PRIORITY = "P0"
CHECK_ID = "DUP_FIGURE_NUM"
DESCRIPTION = "Same Figure/Table/Listing number used multiple times in one file"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

NUM_RE = re.compile(r'(?:Figure|Table|Listing|Code Fragment)\s+(\d+\.\d+(?:\.\d+)?)')

_CAPTION_MARKERS = ('figcaption', 'code-caption', 'diagram-caption', '<caption')


def _is_caption_line(line: str) -> bool:
    low = line.lower()
    return any(m in low for m in _CAPTION_MARKERS)


def run(filepath, html, context):
    issues = []
    occurrences = defaultdict(list)
    for i, line in enumerate(html.split("\n"), 1):
        if not _is_caption_line(line):
            continue
        for m in NUM_RE.finditer(line):
            occurrences[m.group(0)].append(i)
    for label, lines in sorted(occurrences.items()):
        if len(lines) > 1:
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, lines[0],
                f'Duplicate "{label}" on lines: {", ".join(str(l) for l in lines)}'))
    return issues

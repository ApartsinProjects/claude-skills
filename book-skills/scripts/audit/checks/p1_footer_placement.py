"""Check footer placement consistency: inside vs outside <main>.

This is a cross-file check. Per-file run() collects placement data,
then run_cross_file() reports whichever placement is the minority pattern.
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "FOOTER_PLACEMENT"
DESCRIPTION = "Footer placement (inside vs outside <main>) is inconsistent across files"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

MAIN_OPEN_RE = re.compile(r'<main\b[^>]*>', re.IGNORECASE)
MAIN_CLOSE_RE = re.compile(r'</main>', re.IGNORECASE)
FOOTER_RE = re.compile(r'<footer\b[^>]*>', re.IGNORECASE)

# Module-level list to collect per-file results
_file_results = []


def _reset():
    """Clear collected results (useful for repeated runs)."""
    _file_results.clear()


def run(filepath, html, context):
    """Collect footer placement for each file; issues are emitted in run_cross_file."""
    footer_match = FOOTER_RE.search(html)
    if not footer_match:
        return []

    main_open = MAIN_OPEN_RE.search(html)
    main_close = MAIN_CLOSE_RE.search(html)
    if not main_open or not main_close:
        return []

    footer_pos = footer_match.start()
    main_open_pos = main_open.start()
    main_close_pos = main_close.start()

    footer_line = html[:footer_pos].count("\n") + 1

    if main_open_pos < footer_pos < main_close_pos:
        placement = "inside"
    else:
        placement = "outside"

    _file_results.append({
        "filepath": filepath,
        "line": footer_line,
        "placement": placement,
    })

    return []


def run_cross_file(context):
    """Compare all collected placements and flag the minority pattern."""
    issues = []
    if not _file_results:
        return issues

    inside = [r for r in _file_results if r["placement"] == "inside"]
    outside = [r for r in _file_results if r["placement"] == "outside"]

    if not inside or not outside:
        # All consistent, nothing to report
        _reset()
        return issues

    # The minority group is inconsistent
    if len(inside) <= len(outside):
        minority = inside
        minority_label = "inside <main>"
        majority_label = "outside <main>"
    else:
        minority = outside
        minority_label = "outside <main>"
        majority_label = "inside <main>"

    for entry in minority:
        issues.append(Issue(PRIORITY, CHECK_ID, entry["filepath"], entry["line"],
            f'<footer> is {minority_label} (majority pattern: {majority_label}, '
            f'{len(_file_results) - len(minority)}/{len(_file_results)} files)'))

    _reset()
    return issues

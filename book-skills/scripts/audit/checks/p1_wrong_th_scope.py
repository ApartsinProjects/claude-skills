"""Flag <th scope="row"> in header rows where scope should be "col"."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "WRONG_TH_SCOPE"
DESCRIPTION = "Header-row <th> uses scope='row' when it should be scope='col'"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# A row that contains ONLY <th> cells (no <td>) is a header row.
# In such rows, scope should be "col", not "row".
_TR_LINE = re.compile(r"<tr\b[^>]*>")
_TH_WRONG = re.compile(r'<th\s+scope="row">')
_TD_TAG = re.compile(r"<td[\s>]")
_TR_CLOSE = re.compile(r"</tr>")


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    in_tr = False
    tr_start = 0
    tr_lines = []

    for i, line in enumerate(lines, 1):
        if _TR_LINE.search(line):
            in_tr = True
            tr_start = i
            tr_lines = [line]
        elif in_tr:
            tr_lines.append(line)

        if in_tr and _TR_CLOSE.search(line):
            in_tr = False
            block = " ".join(tr_lines)
            # Only flag rows that are all-<th> (no <td> present)
            has_td = _TD_TAG.search(block)
            has_wrong_scope = _TH_WRONG.search(block)
            if not has_td and has_wrong_scope:
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, tr_start,
                    "Header row uses <th scope=\"row\"> but should use "
                    "scope=\"col\" for column headers"
                ))

    return issues

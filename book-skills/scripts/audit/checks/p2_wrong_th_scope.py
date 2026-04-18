"""Check for th elements with scope='row' that appear to be column headers."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "WRONG_TH_SCOPE"
DESCRIPTION = "<th scope='row'> used for column headers (should be scope='col')"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match a row of multiple <th scope="row"> on the same line or within a <tr>
TH_SCOPE_ROW_RE = re.compile(r'<th\s+scope="row"[^>]*>(.*?)</th>', re.IGNORECASE)
TR_OPEN_RE = re.compile(r'<tr\b', re.IGNORECASE)
TR_CLOSE_RE = re.compile(r'</tr>', re.IGNORECASE)
THEAD_OPEN_RE = re.compile(r'<thead\b', re.IGNORECASE)
THEAD_CLOSE_RE = re.compile(r'</thead>', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    in_thead = False
    in_first_tr = False
    first_tr_passed = False
    row_scope_ths = []
    current_tr_line = 0

    for i, line in enumerate(lines, 1):
        # Track thead sections
        if THEAD_OPEN_RE.search(line):
            in_thead = True
        if THEAD_CLOSE_RE.search(line):
            in_thead = False

        if TR_OPEN_RE.search(line):
            if not first_tr_passed:
                in_first_tr = True
                current_tr_line = i
                row_scope_ths = []

        # Collect scope="row" <th> elements in the current row
        for m in TH_SCOPE_ROW_RE.finditer(line):
            if in_first_tr or in_thead:
                content = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                row_scope_ths.append((i, content))

        if TR_CLOSE_RE.search(line):
            if (in_first_tr or in_thead) and len(row_scope_ths) >= 2:
                # Multiple <th scope="row"> in the first row or thead
                # strongly suggests these are column headers
                for th_line, th_content in row_scope_ths:
                    issues.append(Issue(
                        PRIORITY, CHECK_ID, filepath, th_line,
                        f'<th scope="row"> likely should be scope="col": '
                        f'"{th_content[:50]}"',
                    ))
            if in_first_tr:
                in_first_tr = False
                first_tr_passed = True

    return issues

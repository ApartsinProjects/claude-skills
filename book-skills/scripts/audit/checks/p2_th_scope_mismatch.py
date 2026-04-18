"""Check for <th scope="row"> used on column headers in the first <tr> of a table."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "TH_SCOPE_MISMATCH"
DESCRIPTION = '<th scope="row"> in the first table row likely should be scope="col"'

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TABLE_OPEN = re.compile(r"<table\b", re.IGNORECASE)
TABLE_CLOSE = re.compile(r"</table>", re.IGNORECASE)
THEAD_OPEN = re.compile(r"<thead\b", re.IGNORECASE)
TR_OPEN = re.compile(r"<tr\b", re.IGNORECASE)
TR_CLOSE = re.compile(r"</tr>", re.IGNORECASE)
TH_SCOPE_ROW = re.compile(r'<th\b[^>]*scope\s*=\s*["\']row["\']', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    in_table = False
    first_tr_seen = False
    in_first_tr = False
    has_thead = False

    for i, line in enumerate(lines, 1):
        if TABLE_OPEN.search(line):
            in_table = True
            first_tr_seen = False
            has_thead = False
        if not in_table:
            continue

        if THEAD_OPEN.search(line):
            has_thead = True

        if TR_OPEN.search(line) and not first_tr_seen:
            first_tr_seen = True
            in_first_tr = True

        if in_first_tr:
            for m in TH_SCOPE_ROW.finditer(line):
                # First row of a table without <thead>: scope="row" is suspicious
                if not has_thead:
                    end = line.find("</th>", m.end())
                    content = line[m.end():end][:40] if end > 0 else ""
                    content = re.sub(r"<[^>]+>", "", content).strip()
                    issues.append(Issue(
                        PRIORITY, CHECK_ID, filepath, i,
                        f'First-row <th scope="row"> likely should be scope="col": "{content}"',
                    ))

        if TR_CLOSE.search(line) and in_first_tr:
            in_first_tr = False

        if TABLE_CLOSE.search(line):
            in_table = False
            first_tr_seen = False

    return issues

"""Fix th scope='row' to scope='col' in first-row headers of tables without thead."""
import re
from pathlib import Path

TABLE_OPEN = re.compile(r"<table\b", re.IGNORECASE)
TABLE_CLOSE = re.compile(r"</table>", re.IGNORECASE)
THEAD_OPEN = re.compile(r"<thead\b", re.IGNORECASE)
TR_OPEN = re.compile(r"<tr\b", re.IGNORECASE)
TR_CLOSE = re.compile(r"</tr>", re.IGNORECASE)
SCOPE_ROW = re.compile(r'scope="row"', re.IGNORECASE)

files_fixed = 0

for f in Path(".").rglob("*.html"):
    if any(skip in str(f) for skip in ["vendor", ".git", "node_modules", "deprecated"]):
        continue
    text = f.read_text(encoding="utf-8")
    lines = text.split("\n")

    in_table = False
    first_tr_seen = False
    in_first_tr = False
    has_thead = False
    changed = False

    for i, line in enumerate(lines):
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

        if in_first_tr and not has_thead and SCOPE_ROW.search(line):
            lines[i] = SCOPE_ROW.sub('scope="col"', line)
            changed = True

        if TR_CLOSE.search(line) and in_first_tr:
            in_first_tr = False

        if TABLE_CLOSE.search(line):
            in_table = False
            first_tr_seen = False

    if changed:
        f.write_text("\n".join(lines), encoding="utf-8")
        files_fixed += 1

print(f"Fixed scope in {files_fixed} files")

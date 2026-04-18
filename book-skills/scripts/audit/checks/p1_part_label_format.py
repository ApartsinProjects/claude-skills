"""Check that part-label divs have correct part number (Roman or Arabic OK)."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "PART_LABEL_FORMAT"
DESCRIPTION = "Part label number does not match directory"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

PART_LABEL_RE = re.compile(
    r'<div\s+class="part-label"[^>]*>.*?Part\s+([IVXLC]+|[0-9]+)\s*:',
    re.IGNORECASE,
)

DIR_TO_NUM = {
    "part-1-": 1, "part-2-": 2, "part-3-": 3, "part-4-": 4,
    "part-5-": 5, "part-6-": 6, "part-7-": 7, "part-8-": 8,
    "part-9-": 9, "part-10-": 10,
}

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
}

ROMAN_RE = re.compile(r'^[IVXLC]+$')


def _expected_num(filepath):
    path_str = str(filepath).replace("\\", "/")
    for prefix, num in DIR_TO_NUM.items():
        if prefix in path_str:
            return num
    return None


def run(filepath, html, context):
    issues = []
    expected = _expected_num(filepath)
    if expected is None:
        return []

    for i, line in enumerate(html.split("\n"), 1):
        m = PART_LABEL_RE.search(line)
        if m:
            found = m.group(1)
            is_roman = bool(ROMAN_RE.match(found))

            if is_roman:
                # Roman numerals are valid; only flag if number is wrong
                found_num = ROMAN_TO_INT.get(found.upper())
                if found_num and found_num != expected:
                    issues.append(Issue(
                        PRIORITY, CHECK_ID, filepath, i,
                        f'Part label "Part {found}:" is part {found_num} '
                        f'but directory implies Part {expected}'
                    ))
            elif found.isdigit() and int(found) != expected:
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, i,
                    f'Part label "Part {found}:" but directory implies Part {expected}'
                ))
            break
    return issues

"""Check that decision framework / comparison tables appear after (not before) the items they compare."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "DECISION_FRAMEWORK_EARLY"
DESCRIPTION = "Decision framework or comparison table appears before the methods it references"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Patterns that indicate a summary/decision framework
FRAMEWORK_RE = re.compile(
    r'(?:Decision Framework|Method Comparison|Choosing|When to Use|Comparison of|'
    r'Which .+ to (?:Use|Choose))',
    re.IGNORECASE
)

CALLOUT_TITLE_RE = re.compile(r'<div\s+class="callout-title">(.*?)</div>', re.DOTALL)
TABLE_TITLE_RE = re.compile(r'<div\s+class="comparison-table-title">(.*?)</div>', re.DOTALL)
H2_RE = re.compile(r'<h2[^>]*>(.*?)</h2>', re.DOTALL)
H3_RE = re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL)


def run(filepath, html, context):
    if "section-" not in filepath.name:
        return []

    issues = []
    lines = html.split("\n")
    total_lines = len(lines)

    # Find all decision framework callouts/tables
    for i, line in enumerate(lines, 1):
        for pattern_re in (CALLOUT_TITLE_RE, TABLE_TITLE_RE):
            for m in pattern_re.finditer(line):
                title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if FRAMEWORK_RE.search(title):
                    # Check position: if in first 25% of file, it is likely too early
                    position_pct = i / total_lines * 100
                    if position_pct < 20:
                        issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                            f'"{title}" at {position_pct:.0f}% of file '
                            f'(summary tables work better after the content they summarize)'))

    return issues

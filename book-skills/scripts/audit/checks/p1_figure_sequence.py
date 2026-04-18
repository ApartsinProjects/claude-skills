"""Flag figure and code-fragment captions that are numbered out of sequence."""
import re
from collections import defaultdict, namedtuple

PRIORITY = "P1"
CHECK_ID = "FIGURE_SEQUENCE"
DESCRIPTION = "Figure or Code Fragment captions are numbered out of order or have gaps"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Matches <strong>Figure 26.1.3</strong> or <strong>Code Fragment 9.3.2:</strong>
CAPTION_RE = re.compile(
    r"<strong>\s*(?P<kind>Figure|Code Fragment)\s+"
    r"(?P<prefix>\d+\.\d+)\.(?P<seq>\d+)\s*[:</strong>]",
    re.IGNORECASE,
)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    # Collect all captioned items: (kind, prefix) -> [(seq_num, line_num)]
    groups = defaultdict(list)
    for i, line in enumerate(lines, 1):
        for m in CAPTION_RE.finditer(line):
            kind = m.group("kind").title()
            prefix = m.group("prefix")
            seq = int(m.group("seq"))
            groups[(kind, prefix)].append((seq, i))

    for (kind, prefix), entries in groups.items():
        if len(entries) < 2:
            continue

        # Check ordering: each entry should have a higher seq than the previous
        for idx in range(1, len(entries)):
            prev_seq, prev_line = entries[idx - 1]
            curr_seq, curr_line = entries[idx]
            if curr_seq <= prev_seq:
                issues.append(Issue(
                    priority=PRIORITY,
                    check_id=CHECK_ID,
                    filepath=filepath,
                    line=curr_line,
                    message=(
                        f"{kind} {prefix}.{curr_seq} (line {curr_line}) "
                        f"appears after {kind} {prefix}.{prev_seq} (line {prev_line})"
                    ),
                ))

        # Check for gaps in sequence (starting from 1)
        seq_nums = sorted(set(s for s, _ in entries))
        if seq_nums and seq_nums[0] == 0:
            issues.append(Issue(
                priority=PRIORITY,
                check_id=CHECK_ID,
                filepath=filepath,
                line=entries[0][1],
                message=f"{kind} {prefix}.0 uses zero-based numbering (should start at 1)",
            ))

    return issues

"""Detect code captions that are misaligned from their code blocks.

Checks for:
1. CAPTION_AFTER_WRONG_BLOCK: Two or more consecutive <pre> blocks followed by
   stacked captions (captions not interleaved with their code blocks)
2. CAPTION_BEFORE_CODE: A code-caption div appears before its <pre> block
3. ORPHAN_CAPTION: A code-caption div with no preceding <pre> block within 50 lines
4. STACKED_CAPTIONS: Multiple consecutive code-caption divs with no code block between them
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "CAPTION_MISALIGN"
DESCRIPTION = "Code caption misaligned from its code block"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

PRE_OPEN = re.compile(r'<pre\b')
PRE_CLOSE = re.compile(r'</pre>')
CAPTION_RE = re.compile(r'<div class="code-caption">')
CODE_OUTPUT_RE = re.compile(r'<div class="code-output">')


def run(filepath, html, context):
    if "section-" not in filepath.name:
        return []

    issues = []
    lines = html.split("\n")

    # Build a sequence of events: PRE_OPEN, PRE_CLOSE, CAPTION, CODE_OUTPUT
    events = []
    for i, line in enumerate(lines):
        if PRE_OPEN.search(line):
            events.append(("PRE_OPEN", i + 1))
        if PRE_CLOSE.search(line):
            events.append(("PRE_CLOSE", i + 1))
        if CAPTION_RE.search(line):
            events.append(("CAPTION", i + 1))
        if CODE_OUTPUT_RE.search(line):
            events.append(("CODE_OUTPUT", i + 1))

    # Check for stacked captions (multiple captions with no PRE between them)
    consecutive_captions = []
    for event_type, line_num in events:
        if event_type == "CAPTION":
            consecutive_captions.append(line_num)
        else:
            if len(consecutive_captions) > 1:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, consecutive_captions[0],
                    f"Stacked captions: {len(consecutive_captions)} consecutive code-caption divs "
                    f"with no code block between them (lines {consecutive_captions[0]}-{consecutive_captions[-1]})"))
            consecutive_captions = []

    # Check leftover
    if len(consecutive_captions) > 1:
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, consecutive_captions[0],
            f"Stacked captions: {len(consecutive_captions)} consecutive code-caption divs "
            f"with no code block between them (lines {consecutive_captions[0]}-{consecutive_captions[-1]})"))

    # Check for caption before code (caption followed by PRE_OPEN without intervening PRE_CLOSE)
    for idx, (event_type, line_num) in enumerate(events):
        if event_type == "CAPTION":
            # Look at next non-CODE_OUTPUT event
            for j in range(idx + 1, len(events)):
                next_type, next_line = events[j]
                if next_type == "CODE_OUTPUT":
                    continue
                if next_type == "PRE_OPEN" and next_line - line_num < 5:
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                        f"Caption appears BEFORE code block at line {next_line} (should be after)"))
                break

    # Check for orphan captions (no PRE_CLOSE within 50 lines before)
    pre_close_lines = [ln for t, ln in events if t == "PRE_CLOSE"]
    code_output_lines = [ln for t, ln in events if t == "CODE_OUTPUT"]
    for event_type, line_num in events:
        if event_type == "CAPTION":
            # Find nearest PRE_CLOSE or CODE_OUTPUT before this caption
            nearest = 0
            for pcl in pre_close_lines:
                if pcl < line_num:
                    nearest = max(nearest, pcl)
            for col in code_output_lines:
                if col < line_num:
                    nearest = max(nearest, col)
            if nearest == 0 or (line_num - nearest) > 50:
                issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                    f"Orphan caption: no code block found within 50 lines before this caption"))

    # Deduplicate (stacked captions already reported per-line)
    seen = set()
    deduped = []
    for issue in issues:
        key = (issue.filepath, issue.line, issue.message[:50])
        if key not in seen:
            seen.add(key)
            deduped.append(issue)

    return deduped

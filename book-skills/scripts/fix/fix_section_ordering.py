"""Fix the most common section-ordering violations in section-*.html files.

Fixes applied:
  1. Prerequisites after big-picture: swap so prerequisites comes first.
  2. Whats-next after bibliography: move whats-next block before bibliography.
  3. Callout after bibliography: move callout block(s) before bibliography.

Idempotent: running twice produces no additional changes.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Block extraction helpers ────────────────────────────────────────────────

def find_block(lines, start_idx, open_tag_re):
    """Find a block starting at start_idx (0-based) that matches open_tag_re.

    Returns (start, end) as 0-based line indices (inclusive).
    Handles nested tags of the same type (div or section).
    """
    line = lines[start_idx]
    m = open_tag_re.search(line)
    if not m:
        return None

    # Determine the tag name (div or section)
    tag_m = re.search(r'<(div|section)\b', line)
    if not tag_m:
        return None
    tag = tag_m.group(1)

    depth = 0
    for i in range(start_idx, len(lines)):
        # Count all opens and closes of this tag on the line
        depth += len(re.findall(rf'<{tag}\b', lines[i]))
        depth -= len(re.findall(rf'</{tag}\b', lines[i]))
        if depth <= 0:
            return (start_idx, i)
    # If we never closed, return to end of file (shouldn't happen in valid HTML)
    return (start_idx, len(lines) - 1)


def extract_block(lines, start, end):
    """Return lines[start:end+1] and the remaining lines with that range removed."""
    block = lines[start:end + 1]
    remaining = lines[:start] + lines[end + 1:]
    return block, remaining


def first_line_matching(lines, pattern):
    """Return 0-based index of the first line matching pattern, or None."""
    for i, line in enumerate(lines):
        if pattern.search(line):
            return i
    return None


# ── Compiled patterns ───────────────────────────────────────────────────────

BIG_PICTURE_RE = re.compile(r'class="callout big-picture"')
PREREQUISITES_RE = re.compile(r'class="prerequisites"')
WHATS_NEXT_RE = re.compile(r'class="whats-next"')
BIBLIOGRAPHY_RE = re.compile(r'class="bibliography"')
CALLOUT_RE = re.compile(r'<div\s+class="callout\s')

BIG_PICTURE_OPEN = re.compile(r'<div\s+class="callout big-picture"')
PREREQUISITES_OPEN = re.compile(r'<div\s+class="prerequisites"')
WHATS_NEXT_OPEN = re.compile(r'<div\s+class="whats-next"')
BIBLIOGRAPHY_OPEN = re.compile(r'<(div|section)\s+class="bibliography"')


# ── Fix functions ───────────────────────────────────────────────────────────

def fix_prereqs_after_bigpicture(lines):
    """Fix 1: If big-picture appears before prerequisites, swap them."""
    bp_idx = first_line_matching(lines, BIG_PICTURE_RE)
    pr_idx = first_line_matching(lines, PREREQUISITES_RE)

    if bp_idx is None or pr_idx is None:
        return lines, False
    if pr_idx < bp_idx:
        # Already in correct order
        return lines, False

    # Find both blocks
    bp_block_range = find_block(lines, bp_idx, BIG_PICTURE_OPEN)
    pr_block_range = find_block(lines, pr_idx, PREREQUISITES_OPEN)
    if not bp_block_range or not pr_block_range:
        return lines, False

    bp_start, bp_end = bp_block_range
    pr_start, pr_end = pr_block_range

    bp_block = lines[bp_start:bp_end + 1]
    pr_block = lines[pr_start:pr_end + 1]

    # Build new lines: everything before big-picture, then prerequisites,
    # then whatever was between them, then big-picture, then rest.
    between = lines[bp_end + 1:pr_start]
    new_lines = (
        lines[:bp_start]
        + pr_block
        + ["\n"]
        + bp_block
        + between
        + lines[pr_end + 1:]
    )
    return new_lines, True


def fix_whatsnext_after_bibliography(lines):
    """Fix 2: If whats-next appears after bibliography, move it before."""
    bib_idx = first_line_matching(lines, BIBLIOGRAPHY_RE)
    wn_idx = first_line_matching(lines, WHATS_NEXT_RE)

    if bib_idx is None or wn_idx is None:
        return lines, False
    if wn_idx < bib_idx:
        # Already correct
        return lines, False

    wn_range = find_block(lines, wn_idx, WHATS_NEXT_OPEN)
    if not wn_range:
        return lines, False

    wn_start, wn_end = wn_range
    wn_block = lines[wn_start:wn_end + 1]

    # Remove the whats-next block (and any blank lines immediately after it)
    after = wn_end + 1
    while after < len(lines) and lines[after].strip() == "":
        after += 1
    remaining = lines[:wn_start] + lines[after:]

    # Re-find bibliography position in the remaining lines
    bib_idx2 = first_line_matching(remaining, BIBLIOGRAPHY_RE)
    if bib_idx2 is None:
        return lines, False

    # Insert whats-next just before bibliography, with a blank line separator
    new_lines = (
        remaining[:bib_idx2]
        + wn_block
        + ["\n"]
        + remaining[bib_idx2:]
    )
    return new_lines, True


def fix_callouts_after_bibliography(lines):
    """Fix 3: If any callout div appears after the bibliography start, move it before.

    Handles callouts both inside the bibliography block and after it.
    """
    changed = False

    # We may need multiple passes since moving one callout shifts indices
    while True:
        bib_idx = first_line_matching(lines, BIBLIOGRAPHY_RE)
        if bib_idx is None:
            break

        # Search for callouts anywhere after the bibliography opening line
        found_callout = False
        for i in range(bib_idx + 1, len(lines)):
            if CALLOUT_RE.search(lines[i]):
                callout_range = find_block(lines, i, CALLOUT_RE)
                if not callout_range:
                    break
                c_start, c_end = callout_range
                callout_block = lines[c_start:c_end + 1]

                # Remove the callout block (and trailing blank lines)
                after = c_end + 1
                while after < len(lines) and lines[after].strip() == "":
                    after += 1
                remaining = lines[:c_start] + lines[after:]

                # Re-find bibliography in remaining
                bib_idx2 = first_line_matching(remaining, BIBLIOGRAPHY_RE)
                if bib_idx2 is None:
                    break

                # Insert callout just before bibliography
                lines = (
                    remaining[:bib_idx2]
                    + callout_block
                    + ["\n"]
                    + remaining[bib_idx2:]
                )
                changed = True
                found_callout = True
                break  # restart the while loop to find more

        if not found_callout:
            break

    return lines, changed


# ── Main ────────────────────────────────────────────────────────────────────

def process_file(filepath):
    """Apply all fixes to a single file. Returns list of fix descriptions."""
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()

    lines = original.split("\n")
    fixes_applied = []

    lines, did_fix1 = fix_prereqs_after_bigpicture(lines)
    if did_fix1:
        fixes_applied.append("swapped prerequisites before big-picture")

    lines, did_fix2 = fix_whatsnext_after_bibliography(lines)
    if did_fix2:
        fixes_applied.append("moved whats-next before bibliography")

    lines, did_fix3 = fix_callouts_after_bibliography(lines)
    if did_fix3:
        fixes_applied.append("moved callout(s) before bibliography")

    if fixes_applied:
        new_content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    return fixes_applied


def main():
    section_files = sorted(ROOT.rglob("section-*.html"))
    total_fixes = 0

    for fpath in section_files:
        fixes = process_file(fpath)
        if fixes:
            rel = fpath.relative_to(ROOT)
            for desc in fixes:
                print(f"  FIXED  {rel}  =>  {desc}")
            total_fixes += len(fixes)

    print(f"\nDone. Applied {total_fixes} fix(es) across {len(section_files)} files scanned.")


if __name__ == "__main__":
    main()

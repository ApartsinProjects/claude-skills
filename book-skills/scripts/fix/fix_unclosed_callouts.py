#!/usr/bin/env python3
"""Fix unclosed callout divs caused by quiz-question divs closing with </p>.

The self-check callouts contain quiz-question divs that open with
<div class="quiz-question"> but close with </p> instead of </div>.
This leaves the div unclosed, which cascades to leave the parent
callout unclosed when structural divs (takeaways, whats-next) appear.

Fix strategy:
  Phase 1: Fix quiz-question divs that close with </p> instead of </div>.
           Handles both single-line and multi-line variants.
  Phase 2: Re-check with the same nesting logic the audit uses. If any
           callout is still open at a structural div, insert the needed
           </div> tags before the structural div.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}

# Regex patterns
QUIZ_Q_SINGLE = re.compile(
    r'^(\s*)<div class="quiz-question">(.*)</p>\s*$'
)
QUIZ_Q_OPEN = re.compile(r'^\s*<div class="quiz-question">\s*$')
CALLOUT_OPEN_RE = re.compile(r'<div\s+class="callout\s+[^"]*"')
STRUCTURAL_RE = re.compile(r'<div\s+class="(takeaways|whats-next|prerequisites|objectives)"')
DIV_OPEN_RE = re.compile(r'<div[\s>]')
DIV_CLOSE_RE = re.compile(r'</div>')


def fix_quiz_question_closers(lines):
    """Phase 1: fix quiz-question divs that close with </p>."""
    fixes = 0
    i = 0
    while i < len(lines):
        # Single-line: <div class="quiz-question">...text...</p>
        m = QUIZ_Q_SINGLE.match(lines[i])
        if m:
            indent = m.group(1)
            content = m.group(2)
            lines[i] = f'{indent}<div class="quiz-question">{content}</div>'
            fixes += 1
            i += 1
            continue

        # Multi-line: <div class="quiz-question"> on its own line
        if QUIZ_Q_OPEN.match(lines[i]):
            # Look ahead for the closing </p> before the next <details> or <div>
            for j in range(i + 1, min(i + 10, len(lines))):
                stripped = lines[j].strip()
                if stripped == '</p>':
                    # Replace standalone </p> with </div>
                    lines[j] = lines[j].replace('</p>', '</div>')
                    fixes += 1
                    break
                if stripped.endswith('</p>') and not stripped.startswith('<p'):
                    # Line ends with </p> but is not a <p> tag
                    lines[j] = lines[j][:lines[j].rfind('</p>')] + '</div>'
                    fixes += 1
                    break
                if '<details>' in stripped or '</div>' in stripped:
                    break
        i += 1
    return fixes


def check_and_fix_nesting(lines):
    """Phase 2: insert </div> before structural divs if callout still open."""
    inserts = []  # (line_index, count_of_divs_to_close)
    callout_stack = []  # (start_line_0idx, depth_at_open)
    global_depth = 0

    for i, line in enumerate(lines):
        opens = len(DIV_OPEN_RE.findall(line))
        closes = len(DIV_CLOSE_RE.findall(line))

        if CALLOUT_OPEN_RE.search(line):
            callout_stack.append((i, global_depth))

        if callout_stack and STRUCTURAL_RE.search(line):
            # Structural div inside an unclosed callout
            _, depth_at_open = callout_stack[-1]
            divs_to_close = global_depth - depth_at_open
            if divs_to_close > 0:
                inserts.append((i, divs_to_close))

        global_depth += opens - closes

        while callout_stack and global_depth <= callout_stack[-1][1]:
            callout_stack.pop()

    if not inserts:
        return 0

    # Insert in reverse to preserve indices
    for idx, count in reversed(inserts):
        indent = len(lines[idx]) - len(lines[idx].lstrip())
        closing_tags = '\n'.join(['    ' * (indent // 4) + '</div>'] * count)
        # Check if the line before already has enough </div>
        lines.insert(idx, closing_tags)

    return len(inserts)


def fix_file(filepath):
    text = filepath.read_text(encoding="utf-8")
    lines = text.split('\n')

    phase1_fixes = fix_quiz_question_closers(lines)
    phase2_fixes = check_and_fix_nesting(lines)

    total = phase1_fixes + phase2_fixes
    if total > 0:
        filepath.write_text('\n'.join(lines), encoding="utf-8")
    return phase1_fixes, phase2_fixes


def main():
    total_p1 = 0
    total_p2 = 0
    files_fixed = 0

    for html_file in sorted(ROOT.rglob("*.html")):
        if any(s in html_file.parts for s in SKIP_DIRS):
            continue
        try:
            p1, p2 = fix_file(html_file)
        except Exception as e:
            print(f"ERROR: {html_file.relative_to(ROOT)}: {e}")
            continue
        if p1 + p2 > 0:
            files_fixed += 1
            detail = f"{p1} quiz-question closers"
            if p2:
                detail += f", {p2} nesting inserts"
            print(f"Fixed: {html_file.relative_to(ROOT)} ({detail})")
            total_p1 += p1
            total_p2 += p2

    print(f"\n{files_fixed} files fixed")
    print(f"  Phase 1: {total_p1} quiz-question </p> -> </div>")
    print(f"  Phase 2: {total_p2} </div> inserted before structural divs")


if __name__ == "__main__":
    main()

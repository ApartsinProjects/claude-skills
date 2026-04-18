"""Fix all unclosed <p> tag P1 issues found by the audit.

Handles three patterns:
A) <p>text</div>  /  </p>  -- the </p> and </div> are swapped; fix by
   inserting </p> before </div> and removing the stray </p> line.
B) <p class="quiz-question"> followed by <p> on the next line -- nested <p>
   is invalid; replace outer <p> with <div>.
C) <p> whose content runs into a block element (<div>, <h2>, etc.) without
   closing -- insert </p> before the block element.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

files_fixed = 0
total_fixes = 0


def fix_pattern_a(text: str) -> tuple[str, int]:
    """Fix <p>...</div>\\n  </p> by moving </p> before </div> and dropping stray line."""
    count = 0
    lines = text.split("\n")
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        next_line = lines[i + 1]
        # Line ends with </div> and contains an unclosed <p>
        if re.search(r"<p\b", line) and line.rstrip().endswith("</div>") and "</p>" not in line:
            # Next line should be the stray </p>
            if next_line.strip() == "</p>":
                # Insert </p> before </div>
                lines[i] = re.sub(r"</div>\s*$", "</p></div>", line)
                del lines[i + 1]
                count += 1
                continue
        i += 1
    return "\n".join(lines), count


def fix_pattern_b(text: str) -> tuple[str, int]:
    """Fix <p class="quiz-question"> that contains a nested <p> by converting to <div>.

    Only applies when the next line after the opening <p class="quiz-question">
    starts with another <p> tag (indicating nesting).
    """
    count = 0
    lines = text.split("\n")
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        next_line = lines[i + 1]
        m = re.search(r'<p\s+class="quiz-question"\s*>', line)
        if m and re.search(r"^\s*<p\b", next_line):
            # This <p class="quiz-question"> wraps another <p>: convert to <div>
            lines[i] = line[:m.start()] + '<div class="quiz-question">' + line[m.end():]
            count += 1
        i += 1
    return "\n".join(lines), count


def fix_pattern_c(text: str) -> tuple[str, int]:
    """Fix <p> that runs into a block element without closing.

    Specifically targets: open <p> (possibly multiline) followed by a line
    starting a block element like <div>, <h2>, <ul>, <ol>, <table>, <figure>.
    """
    count = 0
    lines = text.split("\n")
    p_open = False
    p_line = -1

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        p_opens = len(re.findall(r"<p\b", line, re.IGNORECASE))
        p_closes = len(re.findall(r"</p>", line, re.IGNORECASE))

        net = p_opens - p_closes
        if net > 0:
            p_open = True
            p_line = i
        elif net < 0 and p_open:
            p_open = False

        # If a <p> is open and we hit a block-level element on a new line
        if p_open and i > p_line:
            if re.match(
                r"\s*<(div|h[1-6]|ul|ol|table|figure|section|blockquote|pre|hr|nav|header|footer|details)\b",
                line,
                re.IGNORECASE,
            ):
                # Insert </p> before this block element
                indent = len(lines[p_line]) - len(lines[p_line].lstrip())
                # Check if the previous line is blank or has content
                prev = i - 1
                # Insert </p> at end of previous non-blank line, or as new line
                if lines[prev].strip() == "":
                    lines.insert(prev, " " * indent + "</p>")
                else:
                    lines[prev] = lines[prev] + "</p>"
                count += 1
                p_open = False
                i += 1  # skip ahead since we inserted a line
        i += 1

    return "\n".join(lines), count


SKIP = {"vendor", ".git", "node_modules", "deprecated"}

for f in ROOT.rglob("*.html"):
    if any(skip in f.parts for skip in SKIP):
        continue

    text = f.read_text(encoding="utf-8")
    original = text
    fixes = 0

    text, n = fix_pattern_a(text)
    fixes += n

    text, n = fix_pattern_b(text)
    fixes += n

    text, n = fix_pattern_c(text)
    fixes += n

    if fixes > 0:
        f.write_text(text, encoding="utf-8")
        files_fixed += 1
        total_fixes += fixes
        print(f"  {f.relative_to(ROOT)}: {fixes} fix(es)")

print(f"\nFixed {total_fixes} unclosed <p> tags in {files_fixed} files")

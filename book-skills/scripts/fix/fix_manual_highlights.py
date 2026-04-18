"""Remove hand-rolled <span class="kw|cm|nu|st|fn|op|bu"> highlighting inside
<code class="language-*"> blocks, letting Prism.js handle syntax highlighting.

Only strips spans whose class is one of the known manual-highlight classes.
Preserves all other spans and attributes.
"""
import re
from pathlib import Path

# Classes used for manual syntax highlighting that conflict with Prism
HIGHLIGHT_CLASSES = {"kw", "cm", "nu", "st", "fn", "op", "bu", "dt", "cf",
                     "co", "dv", "fl", "im", "ss", "va", "al", "at", "bn",
                     "ch", "cv", "do", "er", "ex", "in", "ot", "pp", "sc",
                     "wa"}

# Pattern to match <span class="XX"> where XX is a highlight class
SPAN_PATTERN = re.compile(
    r'<span\s+class="(' + "|".join(HIGHLIGHT_CLASSES) + r')">(.*?)</span>',
    re.DOTALL
)

# Detect code blocks with language class
CODE_OPEN = re.compile(r'<code\s+class="language-', re.IGNORECASE)
CODE_CLOSE = re.compile(r'</code>', re.IGNORECASE)
PRE_OPEN = re.compile(r'<pre\b', re.IGNORECASE)
PRE_CLOSE = re.compile(r'</pre>', re.IGNORECASE)

files_fixed = 0
total_spans_removed = 0

for f in Path(".").rglob("*.html"):
    if any(skip in str(f) for skip in ["vendor", ".git", "node_modules", "deprecated"]):
        continue

    text = f.read_text(encoding="utf-8")

    # Only process files that have both language-tagged code and highlight spans
    if not CODE_OPEN.search(text):
        continue
    if not SPAN_PATTERN.search(text):
        continue

    lines = text.split("\n")
    in_code_block = False
    changed = False

    for i, line in enumerate(lines):
        if CODE_OPEN.search(line):
            in_code_block = True
        if CODE_CLOSE.search(line) and in_code_block:
            # Process the closing line too, then exit code block
            count = len(SPAN_PATTERN.findall(line))
            if count > 0:
                lines[i] = SPAN_PATTERN.sub(r'\2', line)
                total_spans_removed += count
                changed = True
            in_code_block = False
            continue

        if in_code_block:
            count = len(SPAN_PATTERN.findall(line))
            if count > 0:
                lines[i] = SPAN_PATTERN.sub(r'\2', line)
                total_spans_removed += count
                changed = True

    if changed:
        f.write_text("\n".join(lines), encoding="utf-8")
        files_fixed += 1

print(f"Removed {total_spans_removed} manual highlight spans from {files_fixed} files")

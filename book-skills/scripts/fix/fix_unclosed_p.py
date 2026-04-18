"""Fix <p> tags terminated by </div> instead of </p>.

Pattern: A <p> tag inside a <div> that reaches </div> without a closing </p>.
This inserts </p> before the </div> that terminates the paragraph.
"""
import re
from pathlib import Path

# Match <p> ... </div> where there's no </p> before the </div>
# We look for lines with </div> that close a <p> without </p>

files_fixed = 0
total_fixes = 0

for f in Path(".").rglob("*.html"):
    if any(skip in str(f) for skip in ["vendor", ".git", "node_modules", "deprecated"]):
        continue

    text = f.read_text(encoding="utf-8")
    lines = text.split("\n")
    changed = False

    # Track open <p> tags
    p_open = False
    p_open_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Count p opens and closes on this line
        p_opens = len(re.findall(r"<p\b", line, re.IGNORECASE))
        p_closes = len(re.findall(r"</p>", line, re.IGNORECASE))

        if p_opens > p_closes:
            p_open = True
            p_open_line = i

        if p_closes >= p_opens and p_open and p_closes > 0:
            p_open = False

        # If we hit a </div> while a <p> is open, insert </p> before </div>
        if p_open and re.search(r"^\s*</div>", line):
            # Insert </p> before the </div>
            indent = len(line) - len(line.lstrip())
            spaces = " " * (indent + 2)
            lines[i] = f"{spaces}</p>\n{line}"
            changed = True
            total_fixes += 1
            p_open = False

        # Also handle: line has </div> but the <p> is on the same line with no </p>
        # e.g., <p>Some text</div>
        if not p_open and re.search(r"<p\b[^>]*>[^<]*</div>", line, re.IGNORECASE):
            line_new = re.sub(r"(<p\b[^>]*>(?:(?!</p>).)*?)(</div>)", r"\1</p>\2", line)
            if line_new != line:
                lines[i] = line_new
                changed = True
                total_fixes += 1

    if changed:
        f.write_text("\n".join(lines), encoding="utf-8")
        files_fixed += 1

print(f"Fixed {total_fixes} unclosed <p> tags in {files_fixed} files")

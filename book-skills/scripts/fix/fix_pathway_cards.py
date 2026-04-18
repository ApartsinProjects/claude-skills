"""Convert pathway index cards from <a> wrappers to <div> with link on title only.

This fixes the "everything underlined" issue where the entire card is a hyperlink.
"""
import re
from pathlib import Path

INDEX = Path(r"E:\Projects\LLMCourse\front-matter\pathways\index.html")

html = INDEX.read_text(encoding="utf-8")

# Pattern: <a href="X" class="pathway-link-card"> ... <h3>TITLE</h3> ... </a>
# Convert to: <div class="pathway-link-card"> ... <h3><a href="X">TITLE</a></h3> ... </div>

def convert_card(match):
    href = match.group(1)
    inner = match.group(2)
    # Move the href into the <h3> tag
    inner = re.sub(
        r'<h3>(.*?)</h3>',
        lambda m: f'<h3><a href="{href}">{m.group(1)}</a></h3>',
        inner,
        count=1
    )
    return f'<div class="pathway-link-card">{inner}</div>'

# Match <a href="..." class="pathway-link-card"> ... </a>
# Use DOTALL to match across lines
pattern = r'<a\s+href="([^"]+)"\s+class="pathway-link-card">(.*?)</a>'
new_html, count = re.subn(pattern, convert_card, html, flags=re.DOTALL)

print(f"Converted {count} pathway cards from <a> to <div> wrapper")

if count > 0:
    INDEX.write_text(new_html, encoding="utf-8")
    print(f"Written to {INDEX}")
else:
    print("No cards found to convert. Check the pattern.")

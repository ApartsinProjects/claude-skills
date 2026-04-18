"""
Fix algorithm callout blocks to use proper algo-line-keyword and algo-line-comment spans.

1. Replace <b> tags with <span class="algo-line-keyword"> for algorithm keywords
2. Add <span class="algo-line-comment"> to comment lines (// or #)
"""

import re
from pathlib import Path

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles"}

# Keywords to wrap in algo-line-keyword
KEYWORDS = [
    "function", "procedure", "algorithm", "input", "output", "return",
    "if", "else", "else if", "then", "end if", "endif",
    "for", "for each", "foreach", "end for", "endfor",
    "while", "end while", "endwhile", "do", "until",
    "repeat", "begin", "end", "initialize", "set",
    "compute", "calculate", "update", "append", "add",
    "select", "sample", "generate", "emit", "yield",
    "break", "continue", "pass",
    "Input:", "Output:", "Returns:", "Require:", "Ensure:",
    "Step 1:", "Step 2:", "Step 3:", "Step 4:", "Step 5:",
    "Step 6:", "Step 7:", "Step 8:", "Step 9:", "Step 10:",
]

def find_html_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        files.append(f)
    return sorted(files)

def fix_algorithm_block(block_text):
    """Fix a single algorithm callout block's <pre> content."""
    fixed = block_text

    # 1. Replace <b>keyword</b> with <span class="algo-line-keyword">keyword</span>
    # But only if not already wrapped in algo-line-keyword
    def replace_bold(m):
        content = m.group(1)
        # Don't double-wrap
        if 'algo-line' in content:
            return m.group(0)
        return f'<span class="algo-line-keyword">{content}</span>'

    fixed = re.sub(r'<b>([^<]+)</b>', replace_bold, fixed)

    # 2. Add algo-line-comment to comment lines (// or #) that aren't already wrapped
    lines = fixed.split('\n')
    new_lines = []
    for line in lines:
        # Skip if already has algo-line-comment
        if 'algo-line-comment' in line:
            new_lines.append(line)
            continue

        # Match lines that are comments: start with // or # (after optional whitespace/spans)
        # Also match inline comments at end of lines
        stripped = re.sub(r'<[^>]+>', '', line).strip()

        # Full-line comment
        if stripped.startswith('//') or (stripped.startswith('#') and not stripped.startswith('#!')):
            # Wrap the comment part
            comment_match = re.search(r'(//.*|#.*)', line)
            if comment_match:
                comment = comment_match.group(1)
                line = line.replace(comment, f'<span class="algo-line-comment">{comment}</span>')

        new_lines.append(line)

    return '\n'.join(new_lines)

def fix_file(filepath):
    text = filepath.read_text(encoding="utf-8")
    original = text

    # Find all callout algorithm blocks
    def process_algorithm(match):
        full = match.group(0)
        # Find <pre> blocks within
        def fix_pre(pre_match):
            return fix_algorithm_block(pre_match.group(0))

        return re.sub(r'<pre[^>]*>.*?</pre>', fix_pre, full, flags=re.DOTALL)

    text = re.sub(
        r'<div class="callout algorithm"[^>]*>.*?</div>\s*(?=<(?:div|h[23]|p|section|nav|footer|</main))',
        process_algorithm,
        text,
        flags=re.DOTALL
    )

    changed = text != original
    if changed:
        filepath.write_text(text, encoding="utf-8")
    return changed

def main():
    files = find_html_files()
    print(f"Scanning {len(files)} HTML files for algorithm callouts needing style fixes...\n")

    fixed = 0
    for f in files:
        if fix_file(f):
            fixed += 1
            print(f"  Fixed: {f.relative_to(BASE)}")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {fixed} files with algorithm callouts updated")

if __name__ == "__main__":
    main()

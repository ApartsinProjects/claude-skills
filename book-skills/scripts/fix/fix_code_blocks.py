"""
Fix bare <pre> blocks that lack <code class="language-xxx"> wrappers,
and remove inline color spans from inside <pre> blocks.

Prism.js requires <pre><code class="language-python">...</code></pre> format.
This script finds bare <pre> tags and wraps them properly.
"""

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def detect_language(code_content):
    """Detect programming language from code content."""
    stripped = code_content.strip()
    lines = stripped.split('\n')
    first_line = lines[0].strip() if lines else ''

    # Bash detection (check first, some bash scripts contain Python-like words)
    bash_starts = ['$', '#!', 'pip ', 'curl ', 'wget ', 'git ', 'docker ',
                   'apt', 'npm', 'cd ', 'mkdir', 'ls ', 'ls\n', 'cat ',
                   'export ', 'source ', 'conda ', 'brew ', 'sudo ',
                   'python ', 'python3 ']
    if any(first_line.startswith(prefix) for prefix in bash_starts):
        return 'language-bash'

    # YAML
    if first_line.startswith('---') or (': ' in first_line and not any(
            kw in stripped for kw in ['import ', 'def ', 'class '])):
        # Be careful: only if it looks like YAML, not Python dicts
        yaml_lines = [l for l in lines[:5] if re.match(r'^\w[\w_-]*:\s', l)]
        if len(yaml_lines) >= 2:
            return 'language-yaml'

    # JSON
    if first_line.startswith('{') or first_line.startswith('['):
        # Check if it looks like JSON (has quoted keys)
        if re.search(r'"[^"]+"\s*:', stripped):
            return 'language-json'

    # SQL
    sql_keywords = ['SELECT ', 'FROM ', 'WHERE ', 'INSERT ', 'CREATE TABLE',
                    'ALTER TABLE', 'DROP TABLE']
    if any(kw in stripped.upper()[:200] for kw in sql_keywords):
        return 'language-sql'

    # HTML/markup
    if re.search(r'<(html|div|script|body|head|form|table|ul|ol)\b', stripped[:200], re.I):
        return 'language-markup'

    # JavaScript
    js_patterns = [r'\bfunction\s+\w+', r'\bconst\s+\w+', r'\blet\s+\w+',
                   r'\bvar\s+\w+', r'=>']
    if any(re.search(p, stripped[:500]) for p in js_patterns):
        # But not if it also has Python markers
        if not any(kw in stripped[:500] for kw in ['import ', 'def ', 'class ', 'self.']):
            return 'language-javascript'

    # Python (default for this ML textbook, also explicit detection)
    python_markers = ['import ', 'def ', 'class ', 'from ', 'print(',
                      'torch.', 'self.', '"""', "'''", 'elif ', 'except:',
                      'except ', 'lambda ', 'yield ', 'async def']
    if any(kw in stripped[:1000] for kw in python_markers):
        return 'language-python'

    # Check for @ decorators (Python)
    if re.search(r'^@\w+', stripped, re.MULTILINE):
        return 'language-python'

    # Default: Python (ML/AI textbook)
    return 'language-python'


def strip_color_spans(text):
    """Remove <span style="color:...">...</span> tags, keeping inner text."""
    # Match <span style="color:#xxx"> or <span style="color: #xxx"> etc.
    pattern = r'<span\s+style="color:\s*[^"]*">(.*?)</span>'
    count = 0
    while re.search(pattern, text):
        text, n = re.subn(pattern, r'\1', text)
        count += n
    return text, count


def fix_file(filepath):
    """Fix bare <pre> blocks in a single file. Returns (pre_fixed, spans_removed)."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    pre_fixed = 0
    spans_removed = 0

    # Step 1: Remove color spans inside <pre>...</pre> blocks
    # Find all <pre> blocks (both bare and wrapped)
    def remove_spans_in_pre(match):
        nonlocal spans_removed
        block = match.group(0)
        cleaned, count = strip_color_spans(block)
        spans_removed += count
        return cleaned

    content = re.sub(r'<pre(?:\s[^>]*)?>.*?</pre>', remove_spans_in_pre, content, flags=re.DOTALL)

    # Step 2: Fix bare <pre> blocks (those not followed by <code)
    # Pattern: <pre> NOT followed by <code
    # We need to find <pre> tags that are bare
    # Match <pre> or <pre>content but NOT <pre><code
    def fix_bare_pre(match):
        nonlocal pre_fixed
        full = match.group(0)

        # Extract the opening tag
        open_match = re.match(r'<pre(\s[^>]*)?>', full)
        if not open_match:
            return full

        after_tag = full[open_match.end():]
        # Check if immediately followed by <code
        if after_tag.lstrip().startswith('<code'):
            return full

        # This is a bare <pre> block
        # Get the content between <pre> and </pre>
        inner = full[open_match.end():]
        if inner.endswith('</pre>'):
            inner = inner[:-len('</pre>')]

        lang = detect_language(inner)
        pre_fixed += 1
        return f'{open_match.group(0)}<code class="{lang}">{inner}</code></pre>'

    content = re.sub(r'<pre(?:\s[^>]*)?>.*?</pre>', fix_bare_pre, content, flags=re.DOTALL)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    return pre_fixed, spans_removed


def main():
    # Collect target files
    patterns = [
        os.path.join(ROOT, 'part-*', 'module-*', 'section-*.html'),
        os.path.join(ROOT, 'part-*', 'module-*', 'lecture-notes.html'),
        os.path.join(ROOT, 'appendices', '*', 'section-*.html'),
    ]

    files = []
    for pat in patterns:
        files.extend(glob.glob(pat))

    files = sorted(set(files))
    print(f"Scanning {len(files)} files...")

    total_pre_fixed = 0
    total_spans_removed = 0
    files_modified = 0

    for filepath in files:
        pre_fixed, spans_removed = fix_file(filepath)
        if pre_fixed > 0 or spans_removed > 0:
            files_modified += 1
            rel = os.path.relpath(filepath, ROOT)
            print(f"  {rel}: {pre_fixed} bare <pre> fixed, {spans_removed} color spans removed")
        total_pre_fixed += pre_fixed
        total_spans_removed += spans_removed

    print(f"\nSummary:")
    print(f"  Files scanned:  {len(files)}")
    print(f"  Files modified: {files_modified}")
    print(f"  Bare <pre> fixed:    {total_pre_fixed}")
    print(f"  Color spans removed: {total_spans_removed}")


if __name__ == '__main__':
    main()

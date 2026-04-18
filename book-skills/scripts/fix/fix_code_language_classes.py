"""
Add language class to <pre><code> blocks that lack one.

Heuristic for detecting language:
- Contains 'import ' or 'from ' or 'def ' or 'class ' or 'print(' -> python
- Contains 'function ' or 'const ' or 'let ' or '=>' or 'console.' -> javascript
- Contains 'curl ' or '$ ' at start -> bash
- Contains '<' and '>' and '/' (HTML-like) -> html
- Contains 'SELECT ' or 'CREATE TABLE' or 'INSERT INTO' -> sql
- Contains '{ "' or '": ' (JSON-like) -> json
- Contains '#include' or 'int main' -> cpp
- Contains 'fn ' or 'let mut' or '::' frequently -> rust
- Default: text (generic)
"""

import re
from pathlib import Path
from collections import defaultdict

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles"}

def find_html_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        files.append(f)
    return sorted(files)

def detect_language(code_content):
    """Detect programming language from code content."""
    # Decode HTML entities for analysis
    text = code_content.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    # Python indicators
    py_score = 0
    if re.search(r'\bimport\s+\w+', text): py_score += 3
    if re.search(r'\bfrom\s+\w+\s+import\b', text): py_score += 4
    if re.search(r'\bdef\s+\w+\s*\(', text): py_score += 3
    if re.search(r'\bclass\s+\w+[\(:]', text): py_score += 2
    if re.search(r'\bprint\s*\(', text): py_score += 2
    if re.search(r'\bself\.\w+', text): py_score += 3
    if re.search(r'"""', text): py_score += 2
    if re.search(r'#\s+\w+', text) and not re.search(r'#include', text): py_score += 1
    if re.search(r'\bNone\b', text): py_score += 1
    if re.search(r'\bTrue\b|\bFalse\b', text): py_score += 1
    if re.search(r'\.append\(|\.items\(\)|\.keys\(\)', text): py_score += 2
    if re.search(r'async def |await ', text): py_score += 2
    if re.search(r'pip install', text): py_score += 3
    if re.search(r'torch\.|nn\.|tensor', text): py_score += 3
    if re.search(r'numpy|pandas|sklearn|transformers', text): py_score += 3

    # JavaScript/TypeScript indicators
    js_score = 0
    if re.search(r'\bfunction\s+\w+', text): js_score += 3
    if re.search(r'\bconst\s+\w+', text): js_score += 3
    if re.search(r'\blet\s+\w+', text): js_score += 2
    if re.search(r'=>', text): js_score += 2
    if re.search(r'console\.\w+', text): js_score += 3
    if re.search(r'\brequire\(', text): js_score += 3
    if re.search(r'async\s+function|\.then\(', text): js_score += 2
    if re.search(r'npm\s+install', text): js_score += 3

    # Bash/shell indicators
    bash_score = 0
    if re.search(r'^\$\s', text, re.MULTILINE): bash_score += 4
    if re.search(r'\bcurl\s', text): bash_score += 3
    if re.search(r'\bwget\s', text): bash_score += 3
    if re.search(r'\bsudo\s', text): bash_score += 3
    if re.search(r'\bchmod\s', text): bash_score += 3
    if re.search(r'\becho\s', text): bash_score += 2
    if re.search(r'\bexport\s+\w+=', text): bash_score += 3
    if re.search(r'pip install|python\s', text): bash_score += 2
    if re.search(r'\bmkdir\s|\brm\s|\bls\s|\bcd\s', text): bash_score += 2
    if re.search(r'#!/bin/', text): bash_score += 5

    # SQL indicators
    sql_score = 0
    if re.search(r'\bSELECT\b', text, re.IGNORECASE): sql_score += 3
    if re.search(r'\bFROM\b.*\bWHERE\b', text, re.IGNORECASE | re.DOTALL): sql_score += 3
    if re.search(r'\bCREATE\s+TABLE\b', text, re.IGNORECASE): sql_score += 4
    if re.search(r'\bINSERT\s+INTO\b', text, re.IGNORECASE): sql_score += 4

    # JSON indicators
    json_score = 0
    stripped = text.strip()
    if stripped.startswith('{') and stripped.endswith('}'): json_score += 3
    if re.search(r'"[^"]+"\s*:\s*["\[{0-9]', text): json_score += 3

    # HTML/XML indicators
    html_score = 0
    if re.search(r'<\w+[^>]*>', text) and re.search(r'</\w+>', text): html_score += 2
    if re.search(r'<!DOCTYPE', text): html_score += 4
    if re.search(r'<html|<div|<span|<body', text): html_score += 3

    # YAML indicators
    yaml_score = 0
    if re.search(r'^\w+:\s*$', text, re.MULTILINE): yaml_score += 2
    if re.search(r'^\s+-\s+\w+', text, re.MULTILINE): yaml_score += 1
    if re.search(r'^---\s*$', text, re.MULTILINE): yaml_score += 3

    scores = {
        "python": py_score,
        "javascript": js_score,
        "bash": bash_score,
        "sql": sql_score,
        "json": json_score,
        "html": html_score,
        "yaml": yaml_score,
    }

    best = max(scores, key=scores.get)
    if scores[best] >= 3:
        return best
    return "text"

def fix_file(filepath):
    text = filepath.read_text(encoding="utf-8")
    fixes = []

    def replace_code_tag(match):
        full = match.group(0)
        pre_part = match.group(1)
        code_content = match.group(2)

        # Already has a language class
        if 'class="language-' in full:
            return full

        lang = detect_language(code_content)
        fixes.append(lang)
        return f'{pre_part}<code class="language-{lang}">{code_content}'

    # Match <pre><code> or <pre>\n<code> without language class
    new_text = re.sub(
        r'(<pre>\s*)<code>([^<]{0,2000})',
        replace_code_tag,
        text,
        flags=re.DOTALL
    )

    if fixes:
        filepath.write_text(new_text, encoding="utf-8")

    return fixes

def main():
    files = find_html_files()
    print(f"Scanning {len(files)} HTML files for code blocks without language class...\n")

    total_fixes = 0
    files_fixed = 0
    lang_counts = defaultdict(int)

    for f in files:
        fixes = fix_file(f)
        if fixes:
            files_fixed += 1
            total_fixes += len(fixes)
            rel = f.relative_to(BASE)
            langs = defaultdict(int)
            for lang in fixes:
                langs[lang] += 1
                lang_counts[lang] += 1
            lang_str = ", ".join(f"{l}:{c}" for l, c in sorted(langs.items()))
            print(f"  {rel}: {len(fixes)} blocks ({lang_str})")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_fixes} code blocks fixed in {files_fixed} files")
    print(f"\nLanguage distribution:")
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        print(f"  {lang}: {count}")

if __name__ == "__main__":
    main()

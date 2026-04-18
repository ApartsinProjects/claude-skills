"""
Detect sequences of consecutive math-block divs without connecting prose text between them.

Flags cases where 2+ math-blocks appear back-to-back with no <p> or explanatory text
in between. These need connecting phrases like "where ... is defined as" or "combining
these, we get".
"""

import re
from pathlib import Path

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles", "agents", "_lab_fragments", "vendor"}

def find_html_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        files.append(f)
    return sorted(files)

def detect_consecutive_math(filepath):
    text = filepath.read_text(encoding="utf-8")
    issues = []

    # Find all math-block positions
    blocks = list(re.finditer(r'<div class="math-block"[^>]*>.*?</div>', text, re.DOTALL))

    for i in range(len(blocks) - 1):
        end_of_current = blocks[i].end()
        start_of_next = blocks[i + 1].start()
        between = text[end_of_current:start_of_next].strip()

        # Remove HTML comments
        between_clean = re.sub(r'<!--.*?-->', '', between).strip()
        # Remove whitespace-only content
        between_text = re.sub(r'<[^>]+>', '', between_clean).strip()

        # Check if there's meaningful prose between them
        has_prose = len(between_text) > 10  # More than trivial text

        if not has_prose:
            # Get line number
            line_num = text[:blocks[i].start()].count('\n') + 1
            # Get a snippet of each formula for context
            formula1 = re.sub(r'<[^>]+>', '', blocks[i].group(0)).strip()[:60]
            formula2 = re.sub(r'<[^>]+>', '', blocks[i+1].group(0)).strip()[:60]
            issues.append({
                "line": line_num,
                "formula1": formula1,
                "formula2": formula2,
                "between": between_text[:40] if between_text else "(empty)",
                "gap_chars": len(between_text),
            })

    return issues

def main():
    files = find_html_files()
    print(f"Scanning {len(files)} HTML files for consecutive math blocks without prose...\n")

    total = 0
    files_with_issues = 0
    all_issues = []

    for f in files:
        issues = detect_consecutive_math(f)
        if issues:
            files_with_issues += 1
            total += len(issues)
            rel = str(f.relative_to(BASE))
            print(f"  {rel}: {len(issues)} consecutive pairs")
            for issue in issues:
                print(f"    Line {issue['line']}:")
                print(f"      Formula 1: {issue['formula1']}")
                print(f"      Formula 2: {issue['formula2']}")
                print(f"      Between: {issue['between']}")
            all_issues.append((rel, issues))

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total} consecutive math-block pairs without prose in {files_with_issues} files")
    print(f"\nThese need connecting text like:")
    print(f'  "where X is defined as..."')
    print(f'  "Substituting into the equation above, we get..."')
    print(f'  "The dequantization step reverses this process:"')
    print(f'  "Combining these terms:"')

if __name__ == "__main__":
    main()

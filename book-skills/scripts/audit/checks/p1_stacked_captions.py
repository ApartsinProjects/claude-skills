"""
Audit check: P1_STACKED_CAPTIONS
Detects consecutive code-caption divs with no code block (<pre>) between them.
Also detects letter-suffix fragment numbers (e.g., 5a, 5b) which violate numbering rules.

Pattern detected:
  <div class="code-caption">...Code Fragment X...</div>
  <div class="code-caption">...Code Fragment Y...</div>
  (no <pre> between them)

This indicates either:
  - A misplaced caption (should be after its own code block)
  - A missing code block (the shortcut code was never inserted)
  - Two captions accidentally placed on the same code block
"""

import re
import os
import json
import sys


def check_file(filepath):
    """Check a single HTML file for stacked captions and letter suffixes."""
    issues = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    lines = content.split("\n")

    # Find all code-caption div positions
    caption_lines = []
    pre_lines = []

    for i, line in enumerate(lines, 1):
        if 'class="code-caption"' in line:
            # Extract the fragment label
            match = re.search(r'Code Fragment ([\d.]+[a-zA-Z]?)', line)
            label = match.group(1) if match else "unknown"
            caption_lines.append((i, label, line.strip()[:120]))
        if "<pre" in line.lower():
            pre_lines.append(i)

    # Check for stacked captions: consecutive caption divs with no <pre> between them
    for idx in range(len(caption_lines) - 1):
        line_a, label_a, text_a = caption_lines[idx]
        line_b, label_b, text_b = caption_lines[idx + 1]

        # Check if there is any <pre> tag between these two captions
        has_pre_between = any(p > line_a and p < line_b for p in pre_lines)

        if not has_pre_between:
            # Count non-empty lines between the two captions
            between_lines = [
                l for l in lines[line_a:line_b - 1]
                if l.strip()
            ]
            # If there are more than 5 non-empty lines between them,
            # they likely have significant structural HTML separating them
            # (closing divs, new section divs, headings, paragraphs) and
            # are not truly stacked.
            if len(between_lines) > 5:
                continue

            issues.append({
                "type": "STACKED_CAPTION",
                "priority": "P1",
                "line": line_a,
                "label_a": label_a,
                "label_b": label_b,
                "message": f"Stacked captions: Code Fragment {label_a} (line {line_a}) and Code Fragment {label_b} (line {line_b}) have no <pre> block between them"
            })

    # Check for letter suffix numbering (e.g., 5a, 5b, 20.1.4a)
    for line_num, label, text in caption_lines:
        if re.search(r'\d+[a-zA-Z]$', label):
            issues.append({
                "type": "LETTER_SUFFIX",
                "priority": "P1",
                "line": line_num,
                "label": label,
                "message": f"Code Fragment {label} uses letter suffix numbering. Use sequential integers instead (e.g., 5, 6 not 5a, 5b)"
            })

    return issues


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    results = {}
    total_stacked = 0
    total_suffix = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip archive directories
        if "_archive" in dirpath or "node_modules" in dirpath:
            continue

        for fname in sorted(filenames):
            if not fname.startswith("section-") or not fname.endswith(".html"):
                continue

            filepath = os.path.join(dirpath, fname)
            issues = check_file(filepath)

            if issues:
                relpath = os.path.relpath(filepath, root)
                results[relpath] = issues
                for issue in issues:
                    if issue["type"] == "STACKED_CAPTION":
                        total_stacked += 1
                    elif issue["type"] == "LETTER_SUFFIX":
                        total_suffix += 1

    # Print summary
    print(f"=== Stacked Captions & Letter Suffix Audit ===")
    print(f"Total stacked caption pairs: {total_stacked}")
    print(f"Total letter suffix labels: {total_suffix}")
    print(f"Files with issues: {len(results)}")
    print()

    for relpath, issues in sorted(results.items()):
        for issue in issues:
            print(f"[{issue['priority']}] {issue['type']} | {relpath}:{issue['line']} | {issue['message']}")

    # Also output JSON for programmatic use
    if "--json" in sys.argv:
        print("\n--- JSON ---")
        print(json.dumps(results, indent=2))

    return total_stacked + total_suffix


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)

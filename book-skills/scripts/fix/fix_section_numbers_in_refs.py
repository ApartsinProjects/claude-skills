#!/usr/bin/env python3
"""Fix section file number references that still use old numbering.

After module directory renames, some hrefs point to e.g.:
  module-09-inference-optimization/section-8.1.html
when the actual file is section-9.1.html.

This script maps old section prefixes to new ones based on the module renumbering.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Old section prefix -> New section prefix (matching the module renumbering)
# Format: (module_dir_substring, old_section_num, new_section_num)
SECTION_REWRITES = [
    # Part 2: module-09 has section-9.X (was section-8.X from old module-08)
    ("module-09-inference-optimization", "8", "9"),

    # Part 3: module-10 has section-10.X (was section-9.X)
    ("module-10-llm-apis", "9", "10"),
    # module-11 has section-11.X (was section-10.X)
    ("module-11-prompt-engineering", "10", "11"),
    # module-12 has section-12.X (was section-11.X)
    ("module-12-hybrid-ml-llm", "11", "12"),

    # Part 4: each module shifted +1
    ("module-13-synthetic-data", "12", "13"),
    ("module-14-fine-tuning-fundamentals", "13", "14"),
    ("module-15-peft", "14", "15"),
    ("module-16-distillation-merging", "15", "16"),
    ("module-17-alignment-rlhf-dpo", "16", "17"),
    # module-18-interpretability was module-17 (but section files were 17.X -> 18.X)
    ("module-18-interpretability", "17", "18"),

    # Part 5: each module shifted +1
    ("module-19-embeddings-vector-db", "18", "19"),
    ("module-20-rag", "19", "20"),
    ("module-21-conversational-ai", "20", "21"),

    # Also handle the old section-24.8/24.9 -> 28.8/28.9 refs
    ("module-28-llm-applications", "24", "28"),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive"}


def collect_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith((".html", ".json", ".md")):
                yield os.path.join(dirpath, fname)


def main():
    total_files = 0
    total_changes = 0

    for filepath in collect_files(ROOT):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue

        new_content = content
        changes = 0

        for mod_substr, old_sec, new_sec in SECTION_REWRITES:
            # Pattern: module-dir/section-OLD.N.html -> module-dir/section-NEW.N.html
            pattern = f"{mod_substr}/section-{old_sec}."
            replacement = f"{mod_substr}/section-{new_sec}."
            if pattern in new_content:
                new_content = new_content.replace(pattern, replacement)
                changes += 1

            # Also handle: Section OLD.N references in text near module links
            # e.g., "Section 8.1" when referring to content in module-09
            # Skip this for now as it's too risky for false positives

        if changes > 0 and new_content != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            rel = os.path.relpath(filepath, ROOT)
            print(f"  Updated: {rel}")
            total_files += 1
            total_changes += changes

    print(f"\nDone. Updated {total_files} files with {total_changes} section number fixes.")


if __name__ == "__main__":
    main()

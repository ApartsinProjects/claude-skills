#!/usr/bin/env python3
"""Rewrite cross-references from old module numbering to canonical numbering.

The book was restructured from a 7-part to 10-part layout, shifting module numbers.
This script rewrites all references from old to canonical paths.

Old -> Canonical module mapping:
  Part 2: module-08-inference-optimization -> module-09-inference-optimization
  Part 3: module-09-llm-apis -> module-10-llm-apis
          module-10-prompt-engineering -> module-11-prompt-engineering
          module-11-hybrid-ml-llm -> module-12-hybrid-ml-llm
  Part 4: module-12-synthetic-data -> module-13-synthetic-data
          module-13-fine-tuning-fundamentals -> module-14-fine-tuning-fundamentals
          module-14-peft -> module-15-peft
          module-15-distillation-merging -> module-16-distillation-merging
          module-16-alignment-rlhf-dpo -> module-17-alignment-rlhf-dpo
          module-17-interpretability -> module-18-interpretability (moved to Part 2)
  Part 5: module-18-embeddings-vector-db -> module-19-embeddings-vector-db
          module-19-rag -> module-20-rag
          module-20-conversational-ai -> module-21-conversational-ai
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (old_part, old_module, new_part, new_module)
# We only need the module dir name mapping; the part dir names are already canonical
MODULE_REWRITES = [
    # Part 2: old 08-inference -> canonical 09-inference
    ("part-2-understanding-llms", "module-08-inference-optimization",
     "part-2-understanding-llms", "module-09-inference-optimization"),

    # Part 3: old 09-11 -> canonical 10-12
    ("part-3-working-with-llms", "module-09-llm-apis",
     "part-3-working-with-llms", "module-10-llm-apis"),
    ("part-3-working-with-llms", "module-10-prompt-engineering",
     "part-3-working-with-llms", "module-11-prompt-engineering"),
    ("part-3-working-with-llms", "module-11-hybrid-ml-llm",
     "part-3-working-with-llms", "module-12-hybrid-ml-llm"),

    # Part 4: old 12-17 -> canonical 13-18
    ("part-4-training-adapting", "module-12-synthetic-data",
     "part-4-training-adapting", "module-13-synthetic-data"),
    ("part-4-training-adapting", "module-13-fine-tuning-fundamentals",
     "part-4-training-adapting", "module-14-fine-tuning-fundamentals"),
    ("part-4-training-adapting", "module-14-peft",
     "part-4-training-adapting", "module-15-peft"),
    ("part-4-training-adapting", "module-15-distillation-merging",
     "part-4-training-adapting", "module-16-distillation-merging"),
    ("part-4-training-adapting", "module-16-alignment-rlhf-dpo",
     "part-4-training-adapting", "module-17-alignment-rlhf-dpo"),
    ("part-4-training-adapting", "module-17-interpretability",
     "part-2-understanding-llms", "module-18-interpretability"),

    # Part 5: old 18-20 -> canonical 19-21
    ("part-5-retrieval-conversation", "module-18-embeddings-vector-db",
     "part-5-retrieval-conversation", "module-19-embeddings-vector-db"),
    ("part-5-retrieval-conversation", "module-19-rag",
     "part-5-retrieval-conversation", "module-20-rag"),
    ("part-5-retrieval-conversation", "module-20-conversational-ai",
     "part-5-retrieval-conversation", "module-21-conversational-ai"),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive"}


def collect_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith((".html", ".json", ".md", ".css", ".js", ".txt")):
                yield os.path.join(dirpath, fname)


def main():
    total_files = 0
    total_changes = 0

    # Build search patterns: check if file contains any old module path
    old_paths = set()
    for old_part, old_mod, new_part, new_mod in MODULE_REWRITES:
        old_paths.add(f"{old_part}/{old_mod}")
        # Also catch just the module name without part prefix (for within-part refs)
        old_paths.add(old_mod)

    for filepath in collect_files(ROOT):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue

        # Quick check: does file contain any old path?
        if not any(old in content for old in old_paths):
            continue

        new_content = content
        changes = 0

        # Apply rewrites in order (full path first, then bare module name)
        for old_part, old_mod, new_part, new_mod in MODULE_REWRITES:
            old_full = f"{old_part}/{old_mod}"
            new_full = f"{new_part}/{new_mod}"
            if old_full in new_content:
                new_content = new_content.replace(old_full, new_full)
                changes += 1

        # Second pass: bare module dir refs (e.g., href="../module-14-peft/")
        for old_part, old_mod, new_part, new_mod in MODULE_REWRITES:
            # Only replace if old and new are in the same part (avoid ambiguity)
            if old_part == new_part and old_mod in new_content:
                new_content = new_content.replace(old_mod, new_mod)
                changes += 1

        if changes > 0 and new_content != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            rel = os.path.relpath(filepath, ROOT)
            print(f"  Updated: {rel}")
            total_files += 1
            total_changes += changes

    print(f"\nDone. Updated {total_files} files with {total_changes} module path rewrites.")


if __name__ == "__main__":
    main()

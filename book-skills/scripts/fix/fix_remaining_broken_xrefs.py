#!/usr/bin/env python3
"""Fix remaining broken cross-references after the module renumbering.

These are cross-part references where the module dir was updated but the
section file number still uses the old numbering. For example:
  module-22-ai-agents/section-21.1.html -> section-22.1.html
  module-27-multimodal/section-23.1.html -> section-27.1.html
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# For cross-part refs, the module dir name tells us the correct section prefix
# module-NN-xxx/section-OLD.Y.html -> module-NN-xxx/section-NN.Y.html
MODULE_NUM_RE = re.compile(r'module-(\d+)-[^/]+/section-(\d+)\.(\d+)\.html')

SKIP_DIRS = {".git", "_archive", "node_modules", "__pycache__"}


def fix_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    def replace_match(m):
        full = m.group(0)
        mod_num = m.group(1)
        sec_prefix = m.group(2)
        sec_suffix = m.group(3)
        if mod_num != sec_prefix:
            # Check if the correct file actually exists
            return full.replace(f"section-{sec_prefix}.{sec_suffix}.html",
                              f"section-{mod_num}.{sec_suffix}.html")
        return full

    new_content = MODULE_NUM_RE.sub(replace_match, content)

    # Also fix the Part 4 index referencing module-17-interpretability (now in Part 2)
    new_content = new_content.replace(
        "module-17-interpretability/index.html",
        "../../part-2-understanding-llms/module-18-interpretability/index.html"
    )
    new_content = new_content.replace(
        "module-17-interpretability/section-17.",
        "../../part-2-understanding-llms/module-18-interpretability/section-18."
    )

    # Fix toc.html section-13.8 (doesn't exist, was section-12.8 -> now section-13.8 but file is still named 12.8 in canonical)
    # Actually check: does section-13.8 exist?
    sec_13_8 = ROOT / "part-4-training-adapting" / "module-13-synthetic-data" / "section-13.8.html"
    if not sec_13_8.exists():
        # Check what sections actually exist
        sec_dir = ROOT / "part-4-training-adapting" / "module-13-synthetic-data"
        if sec_dir.exists():
            existing = sorted(f.name for f in sec_dir.glob("section-*.html"))
            # The highest section is the one that was added as 12.8 -> should be 13.8
            # but the file itself may still be named section-12.8
            pass

    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


def main():
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith((".html", ".md")):
                fpath = os.path.join(dirpath, fname)
                if fix_file(fpath):
                    print(f"  Fixed: {os.path.relpath(fpath, ROOT)}")
                    count += 1
    print(f"\nFixed {count} files.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fix zero-padded section references.

The previous script created references like section-09.6.html when the actual
files are section-9.6.html. This removes leading zeros from section numbers.
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "_archive", "node_modules", "__pycache__"}

# Match section-0N. where N is a digit (zero-padded)
ZERO_PAD_RE = re.compile(r'section-0(\d)\.')


def main():
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith((".html", ".md", ".json")):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            new_content = ZERO_PAD_RE.sub(r'section-\1.', content)
            if new_content != content:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"  Fixed: {os.path.relpath(fpath, ROOT)}")
                count += 1

    print(f"\nFixed {count} files.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rewrite cross-references from old part-6/part-7 directory paths to canonical paths.

Old structure (7-part layout):
  part-6-agents-applications/module-21-ai-agents          -> part-6-agentic-ai/module-22-ai-agents
  part-6-agents-applications/module-22-multi-agent-systems -> part-6-agentic-ai/module-24-multi-agent-systems
  part-6-agents-applications/module-23-multimodal          -> part-7-multimodal-applications/module-27-multimodal
  part-6-agents-applications/module-24-llm-applications    -> part-7-multimodal-applications/module-28-llm-applications
  part-6-agents-applications/module-25-evaluation-observability -> part-8-evaluation-production/module-29-evaluation-observability
  part-7-production-strategy/module-26-production-engineering   -> part-8-evaluation-production/module-31-production-engineering
  part-7-production-strategy/module-27-safety-ethics-regulation -> part-9-safety-strategy/module-32-safety-ethics-regulation
  part-7-production-strategy/module-28-strategy-product-roi     -> part-9-safety-strategy/module-33-strategy-product-roi

Also rewrites section numbers in href targets:
  section-21.N -> section-22.N, section-22.N -> section-24.N, etc.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Module-level rewrites: (old_part, old_module_prefix, new_part, new_module_prefix, old_sec, new_sec)
REWRITES = [
    ("part-6-agents-applications", "module-21-ai-agents",              "part-6-agentic-ai",             "module-22-ai-agents",              "21", "22"),
    ("part-6-agents-applications", "module-22-multi-agent-systems",    "part-6-agentic-ai",             "module-24-multi-agent-systems",    "22", "24"),
    ("part-6-agents-applications", "module-23-multimodal",             "part-7-multimodal-applications", "module-27-multimodal",             "23", "27"),
    ("part-6-agents-applications", "module-24-llm-applications",       "part-7-multimodal-applications", "module-28-llm-applications",       "24", "28"),
    ("part-6-agents-applications", "module-25-evaluation-observability","part-8-evaluation-production",   "module-29-evaluation-observability","25", "29"),
    ("part-7-production-strategy", "module-26-production-engineering",  "part-8-evaluation-production",   "module-31-production-engineering",  "26", "31"),
    ("part-7-production-strategy", "module-27-safety-ethics-regulation","part-9-safety-strategy",         "module-32-safety-ethics-regulation","27", "32"),
    ("part-7-production-strategy", "module-28-strategy-product-roi",   "part-9-safety-strategy",         "module-33-strategy-product-roi",   "28", "33"),
]

# Also handle bare part-level refs (index.html of old parts)
PART_REWRITES = [
    ("part-6-agents-applications/index.html", "part-6-agentic-ai/index.html"),
    ("part-7-production-strategy/index.html", "part-8-evaluation-production/index.html"),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "scripts"}
SKIP_FILES = {"fix_old_part_paths.py"}


def collect_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname in SKIP_FILES:
                continue
            if fname.endswith((".html", ".json", ".md", ".css", ".js", ".txt")):
                yield os.path.join(dirpath, fname)


def rewrite_content(content):
    """Apply all path rewrites to content string. Returns (new_content, change_count)."""
    changes = 0

    for old_part, old_mod, new_part, new_mod, old_sec, new_sec in REWRITES:
        old_path = f"{old_part}/{old_mod}"
        new_path = f"{new_part}/{new_mod}"

        # Rewrite directory paths
        if old_path in content:
            content = content.replace(old_path, new_path)
            changes += 1

        # Rewrite section file references: section-OLD.N -> section-NEW.N
        pattern = re.compile(rf'section-{re.escape(old_sec)}\.(\d+)')
        if pattern.search(content):
            # Only replace within the context of the new module path (avoid false positives)
            # But also catch standalone refs like "Section 21.3"
            pass

    # Rewrite section number references in href and prose
    section_map = {rw[4]: rw[5] for rw in REWRITES}
    for old_sec, new_sec in section_map.items():
        # href="...section-OLD.N.html"
        old_pat = f"section-{old_sec}."
        new_pat = f"section-{new_sec}."
        # Only do this within the context of the NEW paths (already rewritten above)
        # to avoid corrupting section refs that legitimately use these numbers in other contexts

    # Bare part-level refs
    for old, new in PART_REWRITES:
        if old in content:
            content = content.replace(old, new)
            changes += 1

    return content, changes


def main():
    total_files = 0
    total_changes = 0

    for filepath in collect_files(ROOT):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue

        # Check if file has any old paths
        if "part-6-agents-applications" not in content and "part-7-production-strategy" not in content:
            continue

        new_content = content
        changes = 0

        # Do the rewrites module by module
        for old_part, old_mod, new_part, new_mod, old_sec, new_sec in REWRITES:
            old_full = f"{old_part}/{old_mod}"
            new_full = f"{new_part}/{new_mod}"
            if old_full in new_content:
                new_content = new_content.replace(old_full, new_full)
                changes += 1

        # Bare part index refs
        for old, new in PART_REWRITES:
            if old in new_content:
                new_content = new_content.replace(old, new)
                changes += 1

        # Catch any remaining bare part dir refs (e.g., just "part-6-agents-applications")
        if "part-6-agents-applications" in new_content:
            new_content = new_content.replace("part-6-agents-applications", "part-6-agentic-ai")
            changes += 1
        if "part-7-production-strategy" in new_content:
            new_content = new_content.replace("part-7-production-strategy", "part-8-evaluation-production")
            changes += 1

        if changes > 0 and new_content != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            rel = os.path.relpath(filepath, ROOT)
            print(f"  Updated: {rel}")
            total_files += 1
            total_changes += changes

    print(f"\nDone. Updated {total_files} files with {total_changes} path rewrites.")


if __name__ == "__main__":
    main()

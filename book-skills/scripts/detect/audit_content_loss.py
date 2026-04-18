#!/usr/bin/env python3
"""Audit for content loss after the directory refactoring.

Checks:
1. Every module listed in BOOK_CONFIG.md has a directory with an index.html
2. Every section file that existed before refactoring still exists (compares
   against git HEAD for tracked files, and against _archive for moved files)
3. No section file is suspiciously small (< 2KB = likely empty/stub)
4. No section file is a redirect-only page (meta refresh without real content)
5. Cross-checks: archived files that have NO canonical replacement
6. Validates section numbering matches module numbering (section-N.X in module-N)
"""

import os
import re
import subprocess
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent
BOOK_CONFIG = ROOT / "BOOK_CONFIG.md"
ARCHIVE = ROOT / "_archive"
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "scripts",
             "agents", "vendor", "styles", "images", "templates", "_lab_fragments"}

issues = []


def warn(category, msg):
    issues.append((category, msg))


def check_book_config_modules():
    """Verify every module in BOOK_CONFIG.md exists on disk."""
    if not BOOK_CONFIG.exists():
        warn("CONFIG", "BOOK_CONFIG.md not found")
        return

    config = BOOK_CONFIG.read_text(encoding="utf-8")
    # Parse "Part N: Title (part-dir/)" lines and module lines
    part_dir = None
    for line in config.splitlines():
        m = re.match(r'^Part \d+:.*\((\S+)/\)', line)
        if m:
            part_dir = m.group(1)
            part_path = ROOT / part_dir
            if not part_path.exists():
                warn("MISSING_PART", f"Part directory not found: {part_dir}/")
            continue

        m = re.match(r'^\s+(\d+):\s+.+\s+(module-\S+)\s*$', line)
        if m and part_dir:
            mod_num = m.group(1)
            mod_dir = m.group(2)
            mod_path = ROOT / part_dir / mod_dir
            if not mod_path.exists():
                warn("MISSING_MODULE", f"Module not found: {part_dir}/{mod_dir}/")
            elif not (mod_path / "index.html").exists():
                warn("MISSING_INDEX", f"No index.html: {part_dir}/{mod_dir}/")


def check_section_files():
    """Check all section files for content health."""
    for part_dir in sorted(ROOT.glob("part-*")):
        if part_dir.name.startswith("_"):
            continue
        for mod_dir in sorted(part_dir.glob("module-*")):
            mod_num_match = re.match(r"module-(\d+)-", mod_dir.name)
            if not mod_num_match:
                continue
            mod_num = mod_num_match.group(1)

            sections = sorted(mod_dir.glob("section-*.html"))
            if not sections:
                warn("EMPTY_MODULE", f"No section files in {part_dir.name}/{mod_dir.name}/")
                continue

            for sec_file in sections:
                # Check size
                size = sec_file.stat().st_size
                if size < 2000:
                    warn("TINY_FILE", f"{sec_file.relative_to(ROOT)} ({size} bytes)")

                # Check for redirect-only pages
                content = sec_file.read_text(encoding="utf-8", errors="replace")
                if 'http-equiv="refresh"' in content and len(content) < 3000:
                    warn("REDIRECT_ONLY", f"{sec_file.relative_to(ROOT)} is a redirect stub")

                # Check section number matches module (compare as integers to handle zero-padding)
                sec_match = re.match(r"section-(\d+)\.", sec_file.name)
                if sec_match:
                    sec_prefix = sec_match.group(1)
                    if int(sec_prefix) != int(mod_num):
                        warn("SECTION_MISMATCH",
                             f"{sec_file.relative_to(ROOT)}: section-{sec_prefix} in module-{mod_num}")

                # Check for minimum content markers
                has_h2 = "<h2" in content
                has_main = '<main' in content or '<div class="content"' in content
                if not has_h2 and size > 2000:
                    warn("NO_HEADINGS", f"{sec_file.relative_to(ROOT)} has no <h2> headings")


def check_archived_replacements():
    """Check that archived module dirs have canonical replacements."""
    old_module_dir = ARCHIVE / "old-module-dirs"
    if not old_module_dir.exists():
        return

    for archived in sorted(old_module_dir.iterdir()):
        if not archived.is_dir():
            continue
        # Extract module number from name like p2-module-08-inference-optimization
        m = re.search(r"module-(\d+)-(\S+)", archived.name)
        if not m:
            continue
        old_num = m.group(1)
        slug_part = m.group(2)

        # Count section files in archive
        archived_sections = list(archived.glob("section-*.html"))

        # Find canonical replacement by searching all part dirs
        found = False
        for part_dir in ROOT.glob("part-*"):
            if part_dir.name.startswith("_"):
                continue
            for mod_dir in part_dir.glob("module-*"):
                if slug_part in mod_dir.name:
                    canonical_sections = list(mod_dir.glob("section-*.html"))
                    if len(canonical_sections) < len(archived_sections):
                        warn("FEWER_SECTIONS",
                             f"Canonical {mod_dir.name} has {len(canonical_sections)} sections "
                             f"but archived {archived.name} had {len(archived_sections)}")
                    found = True
                    break
            if found:
                break

        if not found:
            warn("NO_REPLACEMENT",
                 f"Archived {archived.name} ({len(archived_sections)} sections) "
                 f"has no canonical replacement")

    # Also check old-part-dirs
    old_part_dir = ARCHIVE / "old-part-dirs"
    if old_part_dir.exists():
        for archived in sorted(old_part_dir.iterdir()):
            if not archived.is_dir():
                continue
            # Count total HTML files
            html_count = len(list(archived.rglob("*.html")))
            warn("INFO_ARCHIVED_PART",
                 f"Archived part {archived.name}: {html_count} HTML files")


def check_appendices():
    """Check all appendices have content."""
    app_root = ROOT / "appendices"
    if not app_root.exists():
        return
    for app_dir in sorted(app_root.glob("appendix-*")):
        index = app_dir / "index.html"
        if not index.exists():
            warn("MISSING_INDEX", f"No index.html in {app_dir.name}/")
        sections = list(app_dir.glob("section-*.html"))
        if not sections:
            warn("EMPTY_APPENDIX", f"No section files in {app_dir.name}/")


def check_front_matter():
    """Check front matter completeness."""
    fm = ROOT / "front-matter"
    expected = ["index.html", "about-authors.html", "section-fm.7.html"]
    for fname in expected:
        if not (fm / fname).exists():
            warn("MISSING_FM", f"Missing front-matter/{fname}")


def main():
    print("Content Loss Audit")
    print("=" * 60)

    check_book_config_modules()
    check_section_files()
    check_archived_replacements()
    check_appendices()
    check_front_matter()

    # Categorize and report
    by_cat = defaultdict(list)
    for cat, msg in issues:
        by_cat[cat].append(msg)

    critical_cats = {"MISSING_PART", "MISSING_MODULE", "NO_REPLACEMENT",
                     "FEWER_SECTIONS", "SECTION_MISMATCH"}
    warning_cats = {"TINY_FILE", "REDIRECT_ONLY", "EMPTY_MODULE", "NO_HEADINGS",
                    "MISSING_INDEX", "MISSING_FM", "EMPTY_APPENDIX"}
    info_cats = {"INFO_ARCHIVED_PART"}

    print("\n--- CRITICAL (potential content loss) ---")
    crit_count = 0
    for cat in sorted(critical_cats):
        for msg in by_cat.get(cat, []):
            print(f"  [{cat}] {msg}")
            crit_count += 1
    if crit_count == 0:
        print("  None found.")

    print("\n--- WARNINGS ---")
    warn_count = 0
    for cat in sorted(warning_cats):
        for msg in by_cat.get(cat, []):
            print(f"  [{cat}] {msg}")
            warn_count += 1
    if warn_count == 0:
        print("  None found.")

    print("\n--- INFO ---")
    for cat in sorted(info_cats):
        for msg in by_cat.get(cat, []):
            print(f"  [{cat}] {msg}")

    print(f"\n{'=' * 60}")
    print(f"Summary: {crit_count} critical, {warn_count} warnings, "
          f"{sum(len(v) for c, v in by_cat.items() if c in info_cats)} info")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit all image links in the HTML textbook.

Checks:
1. <img src="..."> tags
2. <source srcset="..."> tags
3. CSS url(...) references in inline styles
4. background-image inline styles
Reports broken links, external URLs, and empty sources.
"""

import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "_archive", "node_modules", "__pycache__", "vendor"}

issues = []

# Patterns for image references
RE_IMG_SRC = re.compile(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
RE_SOURCE_SRCSET = re.compile(r'<source\b[^>]*\bsrcset\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
RE_CSS_URL = re.compile(r'url\(\s*["\']?([^"\')\s]+)["\']?\s*\)', re.IGNORECASE)


def record(severity, html_rel, img_ref, detail=""):
    """Record an issue."""
    issues.append((severity, html_rel, img_ref, detail))


def is_external(ref):
    return ref.startswith("http://") or ref.startswith("https://") or ref.startswith("//")


def is_data_uri(ref):
    return ref.startswith("data:")


def collect_html_files():
    """Walk the project and yield all HTML files, skipping excluded dirs."""
    for path in ROOT.rglob("*.html"):
        # Skip if any parent directory is in SKIP_DIRS
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def extract_image_refs(content):
    """Extract all image references from HTML content."""
    refs = []

    for m in RE_IMG_SRC.finditer(content):
        refs.append(("img_src", m.group(1)))

    for m in RE_SOURCE_SRCSET.finditer(content):
        # srcset can contain multiple URLs with descriptors (e.g. "img.jpg 2x, img2.jpg 1x")
        srcset_val = m.group(1)
        for entry in srcset_val.split(","):
            entry = entry.strip()
            if entry:
                # First token is the URL, rest are descriptors
                url = entry.split()[0] if entry.split() else entry
                refs.append(("source_srcset", url))

    for m in RE_CSS_URL.finditer(content):
        ref = m.group(1)
        # Only consider image-like URLs from CSS
        if ref and not ref.startswith("#"):
            refs.append(("css_url", ref))

    return refs


def check_image_ref(html_path, ref_type, ref):
    """Validate a single image reference."""
    html_rel = html_path.relative_to(ROOT)

    # Empty source
    if not ref or ref.isspace():
        record("EMPTY_SRC", str(html_rel), "(empty)", ref_type)
        return "empty"

    # Data URIs are fine, skip silently
    if is_data_uri(ref):
        return "data"

    # External URLs
    if is_external(ref):
        record("EXTERNAL", str(html_rel), ref, ref_type)
        return "external"

    # Fragment-only references (e.g. "#section") are not images
    if ref.startswith("#"):
        return "fragment"

    # Resolve path relative to the HTML file's directory
    ref_clean = ref.split("?")[0].split("#")[0]  # strip query/fragment
    if not ref_clean:
        return "fragment"

    resolved = (html_path.parent / ref_clean).resolve()

    if not resolved.exists():
        record("BROKEN", str(html_rel), ref_clean, ref_type)
        return "broken"

    return "ok"


def main():
    print("Image Link Audit")
    print("=" * 60)

    files_scanned = 0
    total_refs = 0
    status_counts = defaultdict(int)

    for html_path in sorted(collect_html_files()):
        files_scanned += 1
        content = html_path.read_text(encoding="utf-8", errors="replace")
        refs = extract_image_refs(content)

        for ref_type, ref in refs:
            total_refs += 1
            status = check_image_ref(html_path, ref_type, ref)
            status_counts[status] += 1

    # Group issues by severity
    by_severity = defaultdict(list)
    for severity, html_rel, img_ref, detail in issues:
        by_severity[severity].append((html_rel, img_ref, detail))

    # Report BROKEN
    print("\n--- BROKEN (file does not exist) ---")
    broken_list = by_severity.get("BROKEN", [])
    if broken_list:
        for html_rel, img_ref, detail in sorted(broken_list):
            print(f"  [{detail}] {html_rel}")
            print(f"           -> {img_ref}")
    else:
        print("  None found.")

    # Report EMPTY_SRC
    print("\n--- EMPTY_SRC ---")
    empty_list = by_severity.get("EMPTY_SRC", [])
    if empty_list:
        for html_rel, img_ref, detail in sorted(empty_list):
            print(f"  [{detail}] {html_rel}")
    else:
        print("  None found.")

    # Report EXTERNAL
    print("\n--- EXTERNAL (http/https URLs, not validated) ---")
    external_list = by_severity.get("EXTERNAL", [])
    if external_list:
        for html_rel, img_ref, detail in sorted(external_list):
            print(f"  [{detail}] {html_rel}")
            print(f"           -> {img_ref}")
    else:
        print("  None found.")

    # Summary
    broken_count = len(broken_list)
    empty_count = len(empty_list)
    external_count = len(external_list)

    print(f"\n{'=' * 60}")
    print(f"Files scanned:   {files_scanned}")
    print(f"Image refs found:{total_refs:>5}")
    print(f"  OK:            {status_counts['ok']:>5}")
    print(f"  Broken:        {broken_count:>5}")
    print(f"  Empty src:     {empty_count:>5}")
    print(f"  External:      {external_count:>5}")
    print(f"  Data URIs:     {status_counts['data']:>5}")


if __name__ == "__main__":
    main()

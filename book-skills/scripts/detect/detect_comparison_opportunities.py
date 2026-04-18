#!/usr/bin/env python3
"""Detect sections in HTML files that could benefit from a styled comparison table.

Scans all section-*.html and index.html files for:
  1. Existing <table> elements whose headers suggest comparison content
  2. Lists comparing 3+ items with "vs" or "compared to" language
  3. H2/H3 headings like "X vs Y", "Comparison of...", "Choosing between..."
  4. Sections with multiple algorithm/method descriptions side by side

Reports: file path, line number, opportunity type, and a context snippet.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {"node_modules", ".git", "scripts", "styles", "images", "_lab_fragments", "__pycache__"}

# ── pattern constants ──────────────────────────────────────────────────

# Heading patterns that signal comparison
HEADING_VS_RE = re.compile(
    r"<h[23][^>]*>\s*(.*?\bvs\.?\b.*?)</h[23]>", re.IGNORECASE
)
HEADING_COMPARE_RE = re.compile(
    r"<h[23][^>]*>\s*((?:Compar(?:ison|ing)|Choosing [Bb]etween|Differences? [Bb]etween|"
    r"Trade-?offs?|Pros (?:and|&) Cons|When to [Uu]se|Which (?:to|should))[^<]*)</h[23]>",
    re.IGNORECASE,
)

# Inline "vs" / "compared to" inside list items or paragraphs
VS_INLINE_RE = re.compile(
    r"(?:<li>|<p>)[^<]{0,200}?\b(?:vs\.?|versus|compared to|in contrast to)\b",
    re.IGNORECASE,
)

# Table header cells that suggest comparison
TABLE_HEADER_COMPARE_RE = re.compile(
    r"<th[^>]*>[^<]*\b(?:Approach|Method|Algorithm|Model|Library|Framework|Tool|"
    r"Technique|Strategy|Variant|Type|Feature|Pros?|Cons?|Advantage|Disadvantage|"
    r"Strength|Weakness|Trade-?off|Latency|Speed|Cost|Accuracy|When to [Uu]se)\b",
    re.IGNORECASE,
)

# Already wrapped in .comparison-table (skip these)
ALREADY_WRAPPED_RE = re.compile(r'class="comparison-table"', re.IGNORECASE)


def snippet(line: str, max_len: int = 120) -> str:
    """Return a cleaned, truncated snippet of an HTML line."""
    text = re.sub(r"<[^>]+>", "", line).strip()
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def scan_file(filepath: Path) -> list[dict]:
    """Return a list of opportunity dicts for one HTML file."""
    results = []
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return results

    # Quick check: if file already has comparison-table class, note it
    full_text = "\n".join(lines)
    already_has = bool(ALREADY_WRAPPED_RE.search(full_text))

    for i, line in enumerate(lines, start=1):
        # 1. Heading: "X vs Y"
        m = HEADING_VS_RE.search(line)
        if m:
            results.append({
                "file": str(filepath),
                "line": i,
                "type": "heading-vs",
                "snippet": snippet(m.group(1)),
            })

        # 2. Heading: comparison keywords
        m = HEADING_COMPARE_RE.search(line)
        if m:
            results.append({
                "file": str(filepath),
                "line": i,
                "type": "heading-compare",
                "snippet": snippet(m.group(1)),
            })

        # 3. Existing <table> with comparison-style headers
        if "<table" in line.lower() or "<th" in line.lower():
            # Gather the table region (look ahead up to 30 lines for headers)
            region = "\n".join(lines[i - 1: i + 30])
            th_matches = TABLE_HEADER_COMPARE_RE.findall(region)
            if len(th_matches) >= 2 and not already_has:
                results.append({
                    "file": str(filepath),
                    "line": i,
                    "type": "table-compare-headers",
                    "snippet": f"Headers: {', '.join(th_matches[:5])}",
                })

    # 4. Clusters of "vs" / "compared to" in list items (3+ within 30 lines)
    vs_lines = []
    for i, line in enumerate(lines, start=1):
        if VS_INLINE_RE.search(line):
            vs_lines.append(i)

    # Group nearby matches
    if len(vs_lines) >= 2:
        cluster_start = vs_lines[0]
        cluster_count = 1
        for j in range(1, len(vs_lines)):
            if vs_lines[j] - vs_lines[j - 1] <= 30:
                cluster_count += 1
            else:
                if cluster_count >= 2:
                    results.append({
                        "file": str(filepath),
                        "line": cluster_start,
                        "type": "vs-cluster",
                        "snippet": f"{cluster_count} 'vs/compared to' mentions in nearby lines",
                    })
                cluster_start = vs_lines[j]
                cluster_count = 1
        if cluster_count >= 2:
            results.append({
                "file": str(filepath),
                "line": cluster_start,
                "type": "vs-cluster",
                "snippet": f"{cluster_count} 'vs/compared to' mentions in nearby lines",
            })

    return results


def main() -> None:
    all_results: list[dict] = []

    for dirpath, dirnames, filenames in os.walk(ROOT):
        # Prune excluded directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

        for fname in filenames:
            if not fname.endswith(".html"):
                continue
            fpath = Path(dirpath) / fname
            hits = scan_file(fpath)
            all_results.extend(hits)

    # Sort by file, then line
    all_results.sort(key=lambda r: (r["file"], r["line"]))

    # Report
    if not all_results:
        print("No comparison-table opportunities detected.")
        return

    # Summary counts
    type_counts: dict[str, int] = {}
    file_counts: dict[str, int] = {}
    for r in all_results:
        type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
        file_counts[r["file"]] = file_counts.get(r["file"], 0) + 1

    print(f"{'=' * 80}")
    print(f"  Comparison Table Opportunities: {len(all_results)} found across {len(file_counts)} files")
    print(f"{'=' * 80}")
    print()

    print("  By type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        label = {
            "heading-vs": "Heading with 'vs'",
            "heading-compare": "Heading with comparison keyword",
            "table-compare-headers": "Existing table with comparison headers",
            "vs-cluster": "Cluster of vs/compared-to language",
        }.get(t, t)
        print(f"    {label:45s} {c:3d}")
    print()

    # Detailed listing
    current_file = ""
    for r in all_results:
        if r["file"] != current_file:
            current_file = r["file"]
            # Show relative path
            try:
                rel = Path(current_file).relative_to(ROOT)
            except ValueError:
                rel = current_file
            print(f"\n  {rel}")
            print(f"  {'-' * len(str(rel))}")

        tag = r["type"].upper().replace("-", " ")
        print(f"    L{r['line']:>5d}  [{tag:.<28s}]  {r['snippet']}")

    print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Detect <table> elements NOT wrapped in a comparison-table container.

Finds all <table> elements in section HTML files (excluding _archive/) that
are NOT wrapped in either:
  - <div class="comparison-table">
  - <table class="comparison-table">

Reports file path, line number, parent element, column headers, row count,
and whether the table looks like a comparison table.
"""

import os
import re
import sys
from html.parser import HTMLParser

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Patterns that suggest comparative data
COMPARISON_INDICATORS = re.compile(
    r'\b(yes|no|high|medium|low|none|limited|full|partial|good|fair|poor|'
    r'fast|slow|moderate|easy|hard|simple|complex|basic|advanced|'
    r'supported|unsupported|available|unavailable|required|optional|'
    r'true|false|strong|weak|best|worst|better|worse|'
    r'excellent|adequate|minimal|extensive|native|built-in)\b',
    re.IGNORECASE
)
CHECKMARK_PATTERN = re.compile(r'[\u2713\u2714\u2715\u2716\u2717\u2718\u2705\u274C\u274E\u2611\u2612\u25CF\u25CB]|&#x2[67]|&check;|&cross;')
RATING_PATTERN = re.compile(r'\b\d+(\.\d+)?\s*/\s*\d+|\b\d+%|\bstar|rating|\u2605|\u2606', re.IGNORECASE)


class TableFinder(HTMLParser):
    """Parse HTML to find all <table> elements and their context."""

    def __init__(self):
        super().__init__()
        self.tables = []          # list of found table info dicts
        self.tag_stack = []       # stack of (tag, attrs_dict, line)
        self.in_table = False
        self.table_depth = 0
        self.current_table = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.tag_stack.append((tag, attrs_dict, self.getpos()[0]))

        if tag == "table":
            if not self.in_table:
                # Determine parent
                parent_tag = "unknown"
                parent_class = ""
                if len(self.tag_stack) >= 2:
                    parent_tag = self.tag_stack[-2][0]
                    parent_class = self.tag_stack[-2][1].get("class", "")

                table_class = attrs_dict.get("class", "")
                is_wrapped = (
                    "comparison-table" in table_class
                    or (parent_tag == "div" and "comparison-table" in parent_class)
                )

                self.current_table = {
                    "line": self.getpos()[0],
                    "parent_tag": parent_tag,
                    "parent_class": parent_class,
                    "table_class": table_class,
                    "is_wrapped": is_wrapped,
                    "headers": [],
                    "row_count": 0,
                    "in_thead": False,
                    "in_th": False,
                    "in_tbody": False,
                    "current_header_text": "",
                    "all_cell_texts": [],
                    "in_td": False,
                    "current_cell_text": "",
                }
                self.in_table = True
                self.table_depth = 1
            else:
                self.table_depth += 1

        if self.in_table and self.current_table:
            if tag == "thead":
                self.current_table["in_thead"] = True
            elif tag == "tbody":
                self.current_table["in_tbody"] = True
            elif tag == "th" and self.current_table["in_thead"]:
                self.current_table["in_th"] = True
                self.current_table["current_header_text"] = ""
            elif tag == "tr":
                # Count body rows (not header rows)
                if not self.current_table["in_thead"]:
                    self.current_table["row_count"] += 1
            elif tag == "td":
                self.current_table["in_td"] = True
                self.current_table["current_cell_text"] = ""

    def handle_endtag(self, tag):
        if self.in_table and self.current_table:
            if tag == "thead":
                self.current_table["in_thead"] = False
            elif tag == "tbody":
                self.current_table["in_tbody"] = False
            elif tag == "th" and self.current_table["in_th"]:
                self.current_table["in_th"] = False
                header = self.current_table["current_header_text"].strip()
                if header:
                    self.current_table["headers"].append(header)
            elif tag == "td" and self.current_table["in_td"]:
                self.current_table["in_td"] = False
                cell = self.current_table["current_cell_text"].strip()
                if cell:
                    self.current_table["all_cell_texts"].append(cell)

            if tag == "table":
                self.table_depth -= 1
                if self.table_depth == 0:
                    self.tables.append(self.current_table)
                    self.in_table = False
                    self.current_table = None

        # Pop matching tag from stack
        if self.tag_stack:
            # Walk backwards to find matching open tag (handles void elements)
            for i in range(len(self.tag_stack) - 1, -1, -1):
                if self.tag_stack[i][0] == tag:
                    self.tag_stack.pop(i)
                    break

    def handle_data(self, data):
        if self.in_table and self.current_table:
            if self.current_table["in_th"]:
                self.current_table["current_header_text"] += data
            if self.current_table["in_td"]:
                self.current_table["current_cell_text"] += data


def looks_like_comparison(table_info):
    """Heuristic: does this table look like a comparison table?"""
    headers = table_info["headers"]
    col_count = len(headers)
    if col_count < 3:
        return False

    # Check cell contents for comparative indicators
    cells = table_info["all_cell_texts"]
    if not cells:
        return False

    indicator_count = 0
    checkmark_count = 0
    rating_count = 0

    for cell in cells:
        if COMPARISON_INDICATORS.search(cell):
            indicator_count += 1
        if CHECKMARK_PATTERN.search(cell):
            checkmark_count += 1
        if RATING_PATTERN.search(cell):
            rating_count += 1

    total_signals = indicator_count + checkmark_count + rating_count
    # If at least 20% of cells contain comparison signals
    ratio = total_signals / len(cells) if cells else 0
    return ratio >= 0.15


def collect_html_files():
    """Find all section HTML files, excluding _archive/."""
    html_files = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # Skip _archive directories
        dirnames[:] = [d for d in dirnames if d != "_archive"]

        rel = os.path.relpath(dirpath, PROJECT_ROOT).replace("\\", "/")

        # Only look at content directories (parts, appendices, front-matter)
        if rel == ".":
            continue
        top = rel.split("/")[0]
        if top not in (
            "part-1-foundations", "part-2-understanding-llms",
            "part-3-working-with-llms", "part-4-training-adapting",
            "part-5-retrieval-conversation", "part-6-agentic-ai",
            "part-7-multimodal-applications", "part-8-evaluation-production",
            "part-9-safety-strategy", "part-10-frontiers",
            "appendices", "front-matter", "capstone",
        ):
            continue

        for fname in filenames:
            if fname.endswith(".html"):
                html_files.append(os.path.join(dirpath, fname))

    return sorted(html_files)


def analyze_file(filepath):
    """Parse one HTML file and return bare table info."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    parser = TableFinder()
    try:
        parser.feed(content)
    except Exception as e:
        print(f"  WARNING: parse error in {filepath}: {e}", file=sys.stderr)
        return []

    bare_tables = []
    for t in parser.tables:
        if not t["is_wrapped"]:
            bare_tables.append({
                "line": t["line"],
                "parent": f'<{t["parent_tag"]}'
                          + (f' class="{t["parent_class"]}"' if t["parent_class"] else "")
                          + ">",
                "headers": t["headers"],
                "row_count": t["row_count"],
                "is_comparison": looks_like_comparison(t),
                "col_count": len(t["headers"]),
                "table_class": t["table_class"],
            })
    return bare_tables


def main():
    files = collect_html_files()
    print(f"Scanning {len(files)} HTML files for bare <table> elements...\n")

    total_bare = 0
    total_comparison_candidates = 0
    all_results = []

    for fpath in files:
        bare = analyze_file(fpath)
        if not bare:
            continue

        rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")

        for t in bare:
            total_bare += 1
            if t["is_comparison"]:
                total_comparison_candidates += 1

            all_results.append((rel_path, t))

    # Print results grouped: comparison candidates first, then others
    comparison_results = [(r, t) for r, t in all_results if t["is_comparison"]]
    other_results = [(r, t) for r, t in all_results if not t["is_comparison"]]

    if comparison_results:
        print("=" * 80)
        print(f"COMPARISON CANDIDATES ({len(comparison_results)} tables that likely need wrapping)")
        print("=" * 80)
        for rel_path, t in comparison_results:
            _print_table_entry(rel_path, t)

    if other_results:
        print("=" * 80)
        print(f"OTHER BARE TABLES ({len(other_results)} tables without comparison-table wrapper)")
        print("=" * 80)
        for rel_path, t in other_results:
            _print_table_entry(rel_path, t)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Files scanned:              {len(files)}")
    print(f"  Total bare tables found:    {total_bare}")
    print(f"  Comparison candidates:      {total_comparison_candidates}")
    print(f"  Other bare tables:          {total_bare - total_comparison_candidates}")


def _print_table_entry(rel_path, t):
    print(f"\n  File:     {rel_path}")
    print(f"  Line:     {t['line']}")
    print(f"  Parent:   {t['parent']}")
    if t["table_class"]:
        print(f"  Class:    {t['table_class']}")
    headers_str = " | ".join(t["headers"][:8])
    if len(t["headers"]) > 8:
        headers_str += " | ..."
    print(f"  Headers:  [{t['col_count']} cols] {headers_str}")
    print(f"  Rows:     {t['row_count']}")
    print(f"  Comparison? {'YES' if t['is_comparison'] else 'no'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
wrap_comparison_tables.py

Finds comparison-style HTML tables in the LLM textbook and wraps them
in the standardized .comparison-table CSS class with a title bar.

Idempotent: safe to run multiple times. Already-wrapped tables are skipped.
"""

import glob
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories to search
INCLUDE_DIRS = [
    "part-1-foundations",
    "part-2-understanding-llms",
    "part-3-working-with-llms",
    "part-4-training-adapting",
    "part-5-retrieval-conversation",
    "part-6-agentic-ai",
    "part-6-agents-applications",
    "part-7-multimodal-applications",
    "part-7-production-strategy",
    "part-8-evaluation-production",
    "part-9-safety-strategy",
    "part-10-frontiers",
    "appendices",
    "capstone",
]

# Directories to exclude
EXCLUDE_DIRS = {"agents", "templates", "_scripts_archive", "_lab_fragments"}

# Comparison keywords in headers
COMPARISON_HEADER_KW = re.compile(
    r"\b(vs\.?|approach|method|type|strategy|technique|framework|model|tool|"
    r"option|alternative|pros?|cons?|advantage|disadvantage|tradeoff|comparison|"
    r"library|architecture|algorithm|pattern|mode|variant|scheme|format|"
    r"feature|category|dimension|aspect|metric|benchmark|level|tier|"
    r"engine|platform|system|service|provider|solution|implementation|style)\b",
    re.IGNORECASE,
)

# Skip keywords: hyperparameter/config tables, shape traces
SKIP_HEADER_SETS = [
    {"parameter", "value"},
    {"parameter", "default"},
    {"hyperparameter", "value"},
    {"hyperparameter", "default"},
    {"variable", "shape"},
    {"name", "shape"},
    {"tensor", "shape"},
    {"step", "action"},
    {"step", "description"},
    {"epoch", "loss"},
    {"epoch", "train"},
    {"layer", "output shape"},
    {"layer", "parameters"},
]

# Context keywords in preceding headings/paragraphs
CONTEXT_KW = re.compile(
    r"\b(vs\.?|comparison|compared|comparing|choose between|choosing between|"
    r"tradeoffs?|trade-offs?|alternatives|pros and cons|advantages and disadvantages|"
    r"which to use|when to use|differences between)\b",
    re.IGNORECASE,
)


def collect_files():
    """Glob for section-*.html and index.html in content directories."""
    files = []
    for d in INCLUDE_DIRS:
        dirpath = os.path.join(ROOT, d)
        if not os.path.isdir(dirpath):
            continue
        for pattern in ["**/section-*.html", "**/index.html"]:
            for f in glob.glob(os.path.join(dirpath, pattern), recursive=True):
                # Check that no excluded dir is in the path
                parts = os.path.relpath(f, ROOT).replace("\\", "/").split("/")
                if not any(p in EXCLUDE_DIRS for p in parts):
                    files.append(f)
    return sorted(set(files))


def extract_text(html_fragment):
    """Strip HTML tags and return plain text."""
    return re.sub(r"<[^>]+>", "", html_fragment).strip()


def get_headers_from_table(table_html):
    """Extract header cell texts from the first <tr> that contains <th> elements."""
    # Find all <th> in the first row
    # Look for <tr> containing <th>
    th_row = re.search(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
    if not th_row:
        return []
    row_content = th_row.group(1)
    ths = re.findall(r"<th[^>]*>(.*?)</th>", row_content, re.DOTALL | re.IGNORECASE)
    return [extract_text(th) for th in ths]


def count_data_rows(table_html):
    """Count rows that contain <td> elements (data rows, not header rows)."""
    rows = re.findall(r"<tr[^>]*>.*?</tr>", table_html, re.DOTALL | re.IGNORECASE)
    data_rows = 0
    for row in rows:
        if re.search(r"<td[\s>]", row, re.IGNORECASE):
            data_rows += 1
    return data_rows


def should_skip_headers(headers):
    """Check if headers match a skip pattern (config/shape tables)."""
    lower_headers = {h.lower().strip() for h in headers}
    for skip_set in SKIP_HEADER_SETS:
        if skip_set.issubset(lower_headers):
            return True
    # Also skip if first two headers are numeric-pair style
    if len(headers) == 2:
        pair = tuple(h.lower() for h in headers)
        if pair in [("input", "output"), ("before", "after"), ("x", "y")]:
            return True
    return False


def is_comparison_table(headers, preceding_context):
    """Determine if a table is a comparison table based on headers and context."""
    if not headers:
        return False

    # Check header keywords
    header_text = " ".join(headers)
    if COMPARISON_HEADER_KW.search(header_text):
        return True

    # Check if 3+ columns (multi-column tables are more likely comparisons)
    # But only if they have descriptive headers (not just numbers)
    if len(headers) >= 3:
        alpha_headers = sum(1 for h in headers if re.search(r"[a-zA-Z]{2,}", h))
        if alpha_headers >= 2:
            return True

    # Check preceding context
    if CONTEXT_KW.search(preceding_context):
        return True

    return False


def generate_title(headers, preceding_context):
    """Generate a concise title for the comparison table."""
    # Try to use the nearest heading if it describes a comparison
    heading_match = re.findall(
        r"<h[23][^>]*>(.*?)</h[23]>", preceding_context, re.DOTALL | re.IGNORECASE
    )
    if heading_match:
        last_heading = extract_text(heading_match[-1]).strip()
        if len(last_heading) < 60:
            # If heading already says comparison/vs, use it directly
            if CONTEXT_KW.search(last_heading):
                return last_heading
            # Otherwise, append "Comparison" if it fits
            if len(last_heading) < 48:
                return f"{last_heading} Comparison"
            return last_heading

    # Derive from first header cell
    if headers:
        first = headers[0].strip()
        if first and len(first) < 48:
            return f"{first} Comparison"
        elif first:
            return first[:57] + "..."

    return "Comparison"


def is_inside_block(html, table_start, block_patterns):
    """Check if the table at table_start is inside certain block elements."""
    # Search backwards for unclosed blocks
    before = html[:table_start]
    for pattern_open, pattern_close in block_patterns:
        # Count opens and closes before the table position
        opens = len(re.findall(pattern_open, before, re.IGNORECASE))
        closes = len(re.findall(pattern_close, before, re.IGNORECASE))
        if opens > closes:
            return True
    return False


def process_file(filepath, dry_run=False):
    """Process a single HTML file. Returns (tables_found, tables_wrapped, skip_reasons)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    tables_found = 0
    tables_wrapped = 0
    skip_reasons = []

    # Find all <table> ... </table> occurrences
    # We process from end to start so replacements don't shift indices
    table_pattern = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
    matches = list(table_pattern.finditer(content))
    tables_found = len(matches)

    # Process in reverse order to preserve positions
    for match in reversed(matches):
        table_html = match.group(0)
        table_start = match.start()
        table_end = match.end()

        # 1. Already wrapped in comparison-table div?
        # Check the ~200 chars before the table
        before_snippet = content[max(0, table_start - 200):table_start]
        if 'class="comparison-table"' in before_snippet or "class='comparison-table'" in before_snippet:
            skip_reasons.append("already wrapped")
            continue

        # Also check if the table itself has the class (existing misapplied ones)
        if 'class="comparison-table"' in table_html[:60]:
            skip_reasons.append("already has class")
            continue

        # 2. Inside quiz or details block?
        block_patterns = [
            (r'<div[^>]*class="[^"]*quiz[^"]*"[^>]*>', r"</div>"),
            (r"<details[^>]*>", r"</details>"),
        ]
        if is_inside_block(content, table_start, block_patterns):
            skip_reasons.append("inside quiz/details")
            continue

        # 3. Get headers
        headers = get_headers_from_table(table_html)

        # 4. Too few data rows?
        data_rows = count_data_rows(table_html)
        if data_rows < 2:
            skip_reasons.append("too few rows")
            continue

        # 5. Skip hyperparameter/shape tables
        if should_skip_headers(headers):
            skip_reasons.append("config/shape table")
            continue

        # 6. Get preceding context (up to 500 chars before the table)
        context_start = max(0, table_start - 500)
        preceding_context = content[context_start:table_start]

        # 7. Check if this is a comparison table
        if not is_comparison_table(headers, preceding_context):
            skip_reasons.append("not a comparison")
            continue

        # 8. Generate title
        title = generate_title(headers, preceding_context)

        # 9. Determine indentation from the table's line
        line_start = content.rfind("\n", 0, table_start)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
        existing_indent = ""
        for ch in content[line_start:table_start]:
            if ch in " \t":
                existing_indent += ch
            else:
                break

        # 10. Build the wrapper
        inner_indent = existing_indent + "    "
        wrapped = (
            f'{existing_indent}<div class="comparison-table">\n'
            f'{inner_indent}<div class="comparison-table-title">{title}</div>\n'
            f'{inner_indent}{table_html.strip()}\n'
            f'{existing_indent}</div>'
        )

        # Replace the table with the wrapped version
        # We also need to handle the indentation of the original table tag
        # Replace from line_start if the line only contains whitespace before the table
        prefix_on_line = content[line_start:table_start]
        if prefix_on_line.strip() == "":
            # The line has only whitespace before <table>, replace from line_start
            content = content[:line_start] + wrapped + content[table_end:]
        else:
            content = content[:table_start] + wrapped.lstrip() + content[table_end:]

        tables_wrapped += 1

    if content != original and not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return tables_found, tables_wrapped, skip_reasons


def main():
    dry_run = "--dry-run" in sys.argv

    files = collect_files()
    print(f"Scanning {len(files)} HTML files...")
    if dry_run:
        print("(DRY RUN: no files will be modified)\n")

    total_found = 0
    total_wrapped = 0
    total_skipped = 0
    all_skip_reasons = {}
    modified_files = []

    for filepath in files:
        found, wrapped, skip_reasons = process_file(filepath, dry_run=dry_run)
        total_found += found
        total_wrapped += wrapped
        total_skipped += len(skip_reasons)

        for reason in skip_reasons:
            all_skip_reasons[reason] = all_skip_reasons.get(reason, 0) + 1

        if wrapped > 0:
            rel = os.path.relpath(filepath, ROOT).replace("\\", "/")
            modified_files.append((rel, wrapped))

    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total tables found:   {total_found}")
    print(f"Tables wrapped:       {total_wrapped}")
    print(f"Tables skipped:       {total_skipped}")
    print()
    print("Skip reasons:")
    for reason, count in sorted(all_skip_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")
    print()
    print(f"Files modified:       {len(modified_files)}")
    if modified_files:
        print()
        for rel, count in sorted(modified_files):
            print(f"  {rel} ({count} table{'s' if count > 1 else ''})")

    if dry_run:
        print("\n(DRY RUN complete, no files were changed)")


if __name__ == "__main__":
    main()

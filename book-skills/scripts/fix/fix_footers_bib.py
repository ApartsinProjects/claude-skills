#!/usr/bin/env python3
"""Fix footer and bibliography formatting across all HTML files in LLMCourse.

Issue 1: Standardize footers to:
  <footer><p>Fifth Edition, 2026 &middot; <a href="RELATIVE/toc.html">Contents</a></p></footer>

Issue 2: Convert old <ol class="bib-list"> bibliography format to new
  <div class="bib-entry-card"> format.
"""

import os
import re
from pathlib import Path

BASE = Path(r"E:\Projects\LLMCourse")

# Directories to process
INCLUDE_DIRS = [
    "part-1-foundations",
    "part-2-understanding-llms",
    "part-3-working-with-llms",
    "part-4-training-adapting",
    "part-5-retrieval-conversation",
    "part-6-agents-applications",
    "part-6-agentic-ai",
    "part-7-production-strategy",
    "part-7-multimodal-applications",
    "part-8-evaluation-production",
    "part-9-safety-strategy",
    "part-10-frontiers",
    "appendices",
    "front-matter",
    "capstone",
]

EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "agents", "images"}

STANDARD_FOOTER_TEMPLATE = '<footer><p>Fifth Edition, 2026 &middot; <a href="{rel}toc.html">Contents</a></p></footer>'


def get_relative_prefix(filepath: Path) -> str:
    """Determine relative path prefix to toc.html based on file depth."""
    rel = filepath.relative_to(BASE)
    parts = rel.parts  # e.g. ('part-1-foundations', 'module-00-...', 'section-0.1.html')
    depth = len(parts) - 1  # number of directory levels
    if depth == 0:
        return "./"
    return "../" * depth


def collect_html_files() -> list[Path]:
    """Collect all .html files in target directories, excluding unwanted dirs."""
    files = []
    for dirname in INCLUDE_DIRS:
        dirpath = BASE / dirname
        if not dirpath.exists():
            continue
        for root, dirs, fnames in os.walk(dirpath):
            # Prune excluded dirs
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in fnames:
                if fname.endswith(".html"):
                    files.append(Path(root) / fname)
    return sorted(files)


def fix_footer(content: str, filepath: Path) -> tuple[str, str | None]:
    """Fix or insert standard footer. Returns (new_content, action_taken_or_None)."""
    rel_prefix = get_relative_prefix(filepath)
    standard_footer = STANDARD_FOOTER_TEMPLATE.format(rel=rel_prefix)

    # Check if already has the exact standard footer
    if standard_footer in content:
        return content, None

    # Check for existing <footer>...</footer> block (possibly multiline)
    footer_pattern = re.compile(r'<footer>.*?</footer>', re.DOTALL)
    match = footer_pattern.search(content)

    if match:
        existing = match.group(0).strip()
        # Already standard?
        if existing == standard_footer:
            return content, None
        # Replace non-standard footer
        new_content = content[:match.start()] + standard_footer + content[match.end():]
        return new_content, "FOOTER_REPLACED"
    else:
        # No footer found; insert before </main> or </body>
        # Try </main> first
        insert_before = None
        for tag in ["</main>", "</body>"]:
            idx = content.rfind(tag)
            if idx != -1:
                insert_before = (idx, tag)
                break

        if insert_before is None:
            return content, None

        idx, tag = insert_before
        # Insert footer with newline before the closing tag
        indent = "    " if tag == "</main>" else ""
        footer_line = f"\n{indent}{standard_footer}\n"
        new_content = content[:idx] + footer_line + content[idx:]
        return new_content, "FOOTER_INSERTED"


def fix_bib_ol(content: str) -> tuple[str, int]:
    """Convert <ol class="bib-list"> entries to <div class="bib-entry-card"> format.
    Returns (new_content, count_of_ol_blocks_converted).
    """
    count = 0
    # Process each <ol class="bib-list">...</ol> block
    ol_pattern = re.compile(
        r'<ol\s+class="bib-list">\s*(.*?)\s*</ol>',
        re.DOTALL
    )

    def replace_ol(m):
        nonlocal count
        count += 1
        inner = m.group(1)
        # Process each <li>...</li>
        li_pattern = re.compile(r'<li>\s*(.*?)\s*</li>', re.DOTALL)
        cards = []
        for li_match in li_pattern.finditer(inner):
            li_content = li_match.group(1)
            # Extract bib-entry -> bib-ref
            ref_match = re.search(
                r'<p\s+class="bib-entry">(.*?)</p>',
                li_content, re.DOTALL
            )
            # Extract bib-annotation
            ann_match = re.search(
                r'<p\s+class="bib-annotation">(.*?)</p>',
                li_content, re.DOTALL
            )
            ref_text = ref_match.group(1).strip() if ref_match else ""
            ann_text = ann_match.group(1).strip() if ann_match else ""

            card_lines = []
            card_lines.append('    <div class="bib-entry-card">')
            if ref_text:
                card_lines.append(f'        <div class="bib-ref">{ref_text}</div>')
            if ann_text:
                card_lines.append(f'        <div class="bib-annotation">{ann_text}</div>')
            card_lines.append('    </div>')
            cards.append("\n".join(card_lines))

        return "\n".join(cards)

    new_content = ol_pattern.sub(replace_ol, content)
    return new_content, count


def main():
    files = collect_html_files()
    print(f"Scanning {len(files)} HTML files...\n")

    footer_replaced = 0
    footer_inserted = 0
    bib_converted = 0
    bib_files = 0
    files_modified = 0

    for filepath in files:
        content = filepath.read_text(encoding="utf-8")
        original = content
        actions = []

        # Fix footer
        content, footer_action = fix_footer(content, filepath)
        if footer_action == "FOOTER_REPLACED":
            footer_replaced += 1
            actions.append("footer replaced (was non-standard)")
        elif footer_action == "FOOTER_INSERTED":
            footer_inserted += 1
            actions.append("footer inserted (was missing)")

        # Fix bibliography
        content, bib_count = fix_bib_ol(content)
        if bib_count > 0:
            bib_converted += bib_count
            bib_files += 1
            actions.append(f"{bib_count} bib-list block(s) converted")

        # Write if changed
        if content != original:
            filepath.write_text(content, encoding="utf-8")
            files_modified += 1
            rel = filepath.relative_to(BASE)
            print(f"  FIXED  {rel}  [{', '.join(actions)}]")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Files scanned:           {len(files)}")
    print(f"  Files modified:          {files_modified}")
    print(f"  Footers replaced:        {footer_replaced}")
    print(f"  Footers inserted:        {footer_inserted}")
    print(f"  Bib ol blocks converted: {bib_converted}")
    print(f"  Files with bib fixes:    {bib_files}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

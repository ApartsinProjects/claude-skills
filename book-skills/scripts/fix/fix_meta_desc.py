#!/usr/bin/env python3
"""Add missing <meta name="description"> tags to all HTML files in the book."""

import os
import re
import html

ROOT = r"E:\Projects\LLMCourse"
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "templates", "agents"}
BOOK_SUFFIX = "Building Conversational AI textbook"


def collect_html_files(root: str) -> list[str]:
    """Walk the tree and return all .html paths, excluding certain dirs."""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            if fname.endswith(".html"):
                result.append(os.path.join(dirpath, fname))
    result.sort()
    return result


def extract_title(content: str) -> str | None:
    """Extract the text inside <title>...</title>."""
    m = re.search(r"<title>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        return html.unescape(raw)
    return None


def extract_first_paragraph(content: str) -> str | None:
    """Extract text from the first <p> or epigraph block."""
    # Try epigraph first
    m = re.search(r'<(?:blockquote|div)[^>]*class="[^"]*epigraph[^"]*"[^>]*>(.*?)</(?:blockquote|div)>', content, re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.search(r"<p[^>]*>(.*?)</p>", content, re.DOTALL | re.IGNORECASE)
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text).strip()
        text = re.sub(r"\s+", " ", text)
        return text
    return None


def has_meta_description(content: str) -> bool:
    return bool(re.search(r'<meta\s+name="description"', content, re.IGNORECASE))


def build_description(title: str, first_para: str | None) -> str:
    """Create a description under 160 chars from title (and optionally paragraph)."""
    if not title:
        return ""

    # Clean the title: strip trailing pipes or suffixes like "| Book Name"
    clean_title = re.sub(r"\s*\|.*$", "", title).strip()

    # Build the base description from the title
    desc = f"{clean_title}. A comprehensive chapter from the {BOOK_SUFFIX}."

    if len(desc) <= 160:
        return desc

    # If too long, try a shorter suffix
    desc = f"{clean_title}. From the {BOOK_SUFFIX}."
    if len(desc) <= 160:
        return desc

    # If still too long, truncate the title portion
    max_title_len = 160 - len(f". From the {BOOK_SUFFIX}.")
    if max_title_len > 20:
        truncated = clean_title[:max_title_len - 3].rstrip() + "..."
        desc = f"{truncated}. From the {BOOK_SUFFIX}."
        return desc

    # Last resort: just the title truncated to 157 + "..."
    return clean_title[:157] + "..."


def insert_meta_description(content: str, description: str) -> str:
    """Insert <meta name="description"> after the last existing <meta> tag in <head>."""
    meta_tag = f'    <meta name="description" content="{html.escape(description, quote=True)}">'

    # Find the position after the last <meta ...> line before </head> or <link> or <script> or <style> or <title>
    # Strategy: insert right after the <meta name="viewport"> line, or after the last <meta> tag
    # Look for the viewport meta (most files have charset then viewport)
    viewport_match = re.search(
        r'(<meta\s+name="viewport"[^>]*>)\s*\n',
        content,
        re.IGNORECASE,
    )
    if viewport_match:
        insert_pos = viewport_match.end()
        return content[:insert_pos] + meta_tag + "\n" + content[insert_pos:]

    # Fallback: after charset meta
    charset_match = re.search(
        r"(<meta\s+charset[^>]*>)\s*\n",
        content,
        re.IGNORECASE,
    )
    if charset_match:
        insert_pos = charset_match.end()
        return content[:insert_pos] + meta_tag + "\n" + content[insert_pos:]

    # Last fallback: right after <head> or <head ...>
    head_match = re.search(r"(<head[^>]*>)\s*\n", content, re.IGNORECASE)
    if head_match:
        insert_pos = head_match.end()
        return content[:insert_pos] + meta_tag + "\n" + content[insert_pos:]

    return content  # Could not find insertion point


def main():
    files = collect_html_files(ROOT)
    modified = 0
    skipped_already = 0
    skipped_no_title = 0
    skipped_no_head = 0

    for fpath in files:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if has_meta_description(content):
            skipped_already += 1
            continue

        title = extract_title(content)
        if not title:
            skipped_no_title += 1
            continue

        if "<head" not in content.lower():
            skipped_no_head += 1
            continue

        first_para = extract_first_paragraph(content)
        description = build_description(title, first_para)

        if not description:
            continue

        new_content = insert_meta_description(content, description)
        if new_content == content:
            print(f"  WARN: Could not find insertion point: {fpath}")
            continue

        with open(fpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)

        modified += 1

    print(f"\nResults:")
    print(f"  Total HTML files found:     {len(files)}")
    print(f"  Already had description:    {skipped_already}")
    print(f"  Skipped (no <title>):       {skipped_no_title}")
    print(f"  Skipped (no <head>):        {skipped_no_head}")
    print(f"  Files modified:             {modified}")


if __name__ == "__main__":
    main()

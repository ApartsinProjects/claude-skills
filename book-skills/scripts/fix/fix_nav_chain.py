"""
Fix navigation footer chains across the entire book.

Builds the correct sequential reading order across all parts/modules/sections,
then verifies and corrects prev/next links and link text in every
<nav class="chapter-nav"> block.  Also ensures every section file has an
"up" link pointing to its module index.

Usage:
    python scripts/fix/fix_nav_chain.py
"""

import re
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Ordered list of part directories (by numeric key)
PART_DIRS = sorted(
    [d for d in ROOT.iterdir() if d.is_dir() and d.name.startswith("part-")],
    key=lambda d: int(re.search(r"part-(\d+)", d.name).group(1)),
)


def module_sort_key(d):
    """Sort modules by their numeric prefix."""
    m = re.search(r"module-(\d+)", d.name)
    return int(m.group(1)) if m else 999


def section_sort_key(f):
    """Sort section files by their sub-number, e.g. section-22.3 => 3."""
    m = re.search(r"section-\d+\.(\d+)\.html$", f.name)
    return int(m.group(1)) if m else 0


def build_reading_order():
    """
    Build the complete sequential reading order of HTML files.
    For each part: iterate modules in order.
    For each module: index.html, then section-N.1 ... section-N.last.
    Returns a list of Path objects.
    """
    chain = []
    for part_dir in PART_DIRS:
        modules = sorted(
            [d for d in part_dir.iterdir()
             if d.is_dir() and d.name.startswith("module-") and (d / "index.html").exists()],
            key=module_sort_key,
        )
        for mod_dir in modules:
            # Module index first
            chain.append(mod_dir / "index.html")
            # Then section files in order
            sections = sorted(
                [f for f in mod_dir.iterdir()
                 if f.is_file() and re.match(r"section-\d+\.\d+\.html$", f.name)],
                key=section_sort_key,
            )
            chain.extend(sections)
    return chain


def get_h1(filepath):
    """Extract the text content of the first <h1> tag."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL)
    if not m:
        return None
    # Strip inner HTML tags, keep text
    inner = re.sub(r"<[^>]+>", "", m.group(1))
    # Collapse whitespace
    inner = " ".join(inner.split())
    return inner


def get_part_h1(filepath):
    """Get the h1 of the part index for a file's part directory."""
    part_index = filepath.parent.parent / "index.html"
    if not filepath.parent.name.startswith("module-"):
        part_index = filepath.parent / "index.html"
    if part_index.exists():
        return get_h1(part_index)
    return None


def relative_path(from_file, to_file):
    """Compute relative href from from_file to to_file."""
    from_dir = from_file.parent
    try:
        rel = to_file.relative_to(from_dir)
        return str(rel).replace("\\", "/")
    except ValueError:
        pass
    # Build relative path manually
    # Go up from from_dir until we find a common ancestor
    from_parts = from_dir.parts
    to_parts = to_file.parts
    # Find common prefix length
    common = 0
    for a, b in zip(from_parts, to_parts):
        if a == b:
            common += 1
        else:
            break
    ups = len(from_parts) - common
    remainder = to_parts[common:]
    rel = "/".join([".."] * ups + list(remainder))
    return rel


def text_to_html(text):
    """Convert plain text to HTML-safe string for use in link text."""
    return html.escape(text, quote=False)


def parse_nav(content):
    """
    Parse the <nav class="chapter-nav"> block.
    Returns (nav_match, prev_href, prev_text, next_href, next_text, up_href, up_text)
    where nav_match is the regex match object for the entire nav block.
    """
    nav_pat = re.compile(
        r'<nav\s+class="chapter-nav">\s*(.*?)\s*</nav>',
        re.DOTALL,
    )
    m = nav_pat.search(content)
    if not m:
        return None, None, None, None, None, None, None

    block = m.group(1)

    def extract_link(cls):
        pat = re.compile(
            rf'<a\s+[^>]*class="(?:[^"]*\s)?{cls}(?:\s[^"]*)?"\s+href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        lm = pat.search(block)
        if lm:
            return lm.group(1), lm.group(2).strip()
        # Also try href before class
        pat2 = re.compile(
            rf'<a\s+href="([^"]*)"\s+class="(?:[^"]*\s)?{cls}(?:\s[^"]*)?"\s*>(.*?)</a>',
            re.DOTALL,
        )
        lm2 = pat2.search(block)
        if lm2:
            return lm2.group(1), lm2.group(2).strip()
        return None, None

    prev_href, prev_text = extract_link("prev")
    next_href, next_text = extract_link("next")
    up_href, up_text = extract_link("up")

    return m, prev_href, prev_text, next_href, next_text, up_href, up_text


def build_nav_block(prev_href, prev_text, next_href, next_text, up_href, up_text):
    """Build a <nav class="chapter-nav"> block."""
    lines = ['<nav class="chapter-nav">']
    if prev_href:
        lines.append(f'    <a class="prev" href="{prev_href}">{prev_text}</a>')
    if up_href:
        lines.append(f'    <a class="up" href="{up_href}">{up_text}</a>')
    if next_href:
        lines.append(f'    <a class="next" href="{next_href}">{next_text}</a>')
    lines.append('</nav>')
    return "\n".join(lines)


def main():
    chain = build_reading_order()
    print(f"Reading order: {len(chain)} files across {len(PART_DIRS)} parts\n")

    # Pre-compute h1 titles for all files
    h1_cache = {}
    for fp in chain:
        t = get_h1(fp)
        if t:
            h1_cache[fp] = t
        else:
            h1_cache[fp] = fp.parent.name  # fallback

    # Also cache part index h1s
    part_h1 = {}
    for pd in PART_DIRS:
        pi = pd / "index.html"
        if pi.exists():
            part_h1[pd.name] = get_h1(pi) or pd.name

    fixed_count = 0
    issues = {"prev_href": 0, "prev_text": 0, "next_href": 0, "next_text": 0,
              "up_missing": 0, "up_href": 0, "up_text": 0, "nav_missing": 0}

    for i, filepath in enumerate(chain):
        prev_file = chain[i - 1] if i > 0 else None
        next_file = chain[i + 1] if i < len(chain) - 1 else None

        # Determine if this is a module index or section
        is_module_index = filepath.name == "index.html"
        is_section = not is_module_index

        # Compute expected prev
        if prev_file:
            expected_prev_href = relative_path(filepath, prev_file)
            expected_prev_text = text_to_html(h1_cache.get(prev_file, ""))
        else:
            # First file in chain: prev points to its part index
            part_index = filepath.parent.parent / "index.html"
            expected_prev_href = relative_path(filepath, part_index)
            expected_prev_text = text_to_html(
                part_h1.get(filepath.parent.parent.name, "Part Overview")
            )

        # Compute expected next
        if next_file:
            expected_next_href = relative_path(filepath, next_file)
            expected_next_text = text_to_html(h1_cache.get(next_file, ""))
        else:
            # Last file in chain: no next (or could point to appendices)
            expected_next_href = None
            expected_next_text = None

        # Compute expected up (sections point to module index, module index to part)
        if is_section:
            up_target = filepath.parent / "index.html"
            expected_up_href = "index.html"
            expected_up_text = text_to_html(h1_cache.get(up_target, ""))
        else:
            # Module index: up points to part index
            up_target = filepath.parent.parent / "index.html"
            expected_up_href = "../index.html"
            expected_up_text = "Part Overview"

        # Read file
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  ERROR reading {filepath}: {e}")
            continue

        nav_match, cur_prev_href, cur_prev_text, cur_next_href, cur_next_text, cur_up_href, cur_up_text = parse_nav(content)

        if nav_match is None:
            # No nav block at all, skip (we'd need to insert one, but that's a different task)
            issues["nav_missing"] += 1
            continue

        # Determine what needs fixing
        file_issues = []

        # Check prev
        if expected_prev_href and cur_prev_href != expected_prev_href:
            file_issues.append(f"prev href: {cur_prev_href} => {expected_prev_href}")
            issues["prev_href"] += 1
        if expected_prev_href and expected_prev_text and cur_prev_text != expected_prev_text:
            # Normalize both for comparison (handle &amp; etc.)
            cur_decoded = html.unescape(cur_prev_text or "")
            exp_decoded = html.unescape(expected_prev_text)
            if cur_decoded != exp_decoded:
                file_issues.append(f"prev text mismatch")
                issues["prev_text"] += 1

        # Check next
        if expected_next_href:
            if cur_next_href != expected_next_href:
                file_issues.append(f"next href: {cur_next_href} => {expected_next_href}")
                issues["next_href"] += 1
            if expected_next_text:
                cur_decoded = html.unescape(cur_next_text or "")
                exp_decoded = html.unescape(expected_next_text)
                if cur_decoded != exp_decoded:
                    file_issues.append(f"next text mismatch")
                    issues["next_text"] += 1

        # Check up link (for sections)
        if is_section:
            if cur_up_href is None:
                file_issues.append("up link missing")
                issues["up_missing"] += 1
            elif cur_up_href != expected_up_href:
                file_issues.append(f"up href: {cur_up_href} => {expected_up_href}")
                issues["up_href"] += 1

        if not file_issues:
            continue

        # Build corrected nav
        final_prev_href = expected_prev_href
        final_prev_text = expected_prev_text
        # If we don't have expected prev text but have current, keep current
        if not final_prev_text and cur_prev_text:
            final_prev_text = cur_prev_text

        final_next_href = expected_next_href
        final_next_text = expected_next_text
        if not final_next_text and cur_next_text:
            final_next_text = cur_next_text

        # For module index, keep existing up style if present; for sections, ensure up link
        if is_section:
            final_up_href = expected_up_href
            final_up_text = expected_up_text
        elif cur_up_href is not None:
            # Module index had an up link, keep it
            final_up_href = expected_up_href
            final_up_text = expected_up_text
        else:
            final_up_href = cur_up_href
            final_up_text = cur_up_text

        new_nav = build_nav_block(
            final_prev_href, final_prev_text,
            final_next_href, final_next_text,
            final_up_href, final_up_text,
        )

        # Replace old nav with new
        new_content = content[:nav_match.start()] + new_nav + content[nav_match.end():]

        if new_content != content:
            filepath.write_text(new_content, encoding="utf-8")
            rel = filepath.relative_to(ROOT)
            print(f"  FIXED {rel}")
            for iss in file_issues:
                print(f"         {iss}")
            fixed_count += 1

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {fixed_count} files fixed out of {len(chain)} in reading order")
    print(f"\nIssue breakdown:")
    for k, v in sorted(issues.items(), key=lambda x: -x[1]):
        if v > 0:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

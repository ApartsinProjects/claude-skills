#!/usr/bin/env python3
"""Fix three mechanical accessibility issues across all HTML files.

Fix 1: MISSING_TH_SCOPE - Add scope attribute to <th> elements that lack one.
Fix 2: EXT_LINK_ATTRS - Add target="_blank" and rel="noopener" to external links.
Fix 3: EXCESSIVE_BLANKS - Collapse 3+ consecutive blank lines to 2.
"""

import os
import re
import sys

ROOT = r"E:\Projects\LLMCourse"
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__"}

# Counters
counts = {"th_scope": 0, "ext_link": 0, "blanks": 0}
modified_files = set()


def collect_html_files(root):
    """Walk root and yield .html file paths, skipping excluded dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            if fname.endswith(".html"):
                yield os.path.join(dirpath, fname)


# ---------------------------------------------------------------------------
# Fix 1: MISSING_TH_SCOPE
# ---------------------------------------------------------------------------

def is_inside_thead(html, match_start):
    """Check whether the position match_start falls inside a <thead> block."""
    # Find the most recent <thead> or </thead> before this position
    last_thead_open = html.rfind("<thead", 0, match_start)
    last_thead_close = html.rfind("</thead", 0, match_start)
    if last_thead_open == -1:
        return False
    if last_thead_close == -1:
        return True
    return last_thead_open > last_thead_close


# Match <th that does NOT already have scope=
TH_WITHOUT_SCOPE = re.compile(r"<th\b(?![^>]*\bscope\b)([^>]*?)>", re.IGNORECASE)


def fix_th_scope(html):
    """Add scope='col' or scope='row' to <th> elements missing scope."""
    fixed = 0

    def replacer(m):
        nonlocal fixed
        scope_val = "col" if is_inside_thead(html, m.start()) else "row"
        fixed += 1
        # Insert scope right after <th
        return f'<th scope="{scope_val}"{m.group(1)}>'

    new_html = TH_WITHOUT_SCOPE.sub(replacer, html)
    return new_html, fixed


# ---------------------------------------------------------------------------
# Fix 2: EXT_LINK_ATTRS
# ---------------------------------------------------------------------------

# Match <a ...href="http(s)://..."...>
A_TAG_RE = re.compile(r"<a\b([^>]*?)>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r'''href\s*=\s*["'](https?://)''', re.IGNORECASE)
TARGET_RE = re.compile(r'''\btarget\s*=\s*["'][^"']*["']''', re.IGNORECASE)
REL_RE = re.compile(r'''\brel\s*=\s*["']([^"']*)["']''', re.IGNORECASE)


def fix_ext_links(html):
    """Add target='_blank' and rel='noopener' to external links."""
    fixed = 0

    def replacer(m):
        nonlocal fixed
        attrs = m.group(1)
        # Only process if href starts with http:// or https://
        if not HREF_RE.search(attrs):
            return m.group(0)

        changed = False

        # Add target="_blank" if missing
        if not TARGET_RE.search(attrs):
            attrs = attrs + ' target="_blank"'
            changed = True

        # Handle rel: add noopener if missing
        rel_match = REL_RE.search(attrs)
        if rel_match:
            rel_val = rel_match.group(1)
            if "noopener" not in rel_val:
                new_rel = (rel_val + " noopener").strip()
                attrs = attrs[:rel_match.start()] + f'rel="{new_rel}"' + attrs[rel_match.end():]
                changed = True
        else:
            attrs = attrs + ' rel="noopener"'
            changed = True

        if changed:
            fixed += 1
        return f"<a{attrs}>"

    new_html = A_TAG_RE.sub(replacer, html)
    return new_html, fixed


# ---------------------------------------------------------------------------
# Fix 3: EXCESSIVE_BLANKS
# ---------------------------------------------------------------------------

EXCESSIVE_BLANKS_RE = re.compile(r"\n{4,}")


def fix_excessive_blanks(html):
    """Replace 3+ consecutive blank lines with exactly 2."""
    new_html, count = EXCESSIVE_BLANKS_RE.subn(r"\n\n\n", html)
    return new_html, count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    files = list(collect_html_files(ROOT))
    print(f"Scanning {len(files)} HTML files...")

    for fpath in files:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()

        content = original

        content, n1 = fix_th_scope(content)
        counts["th_scope"] += n1

        content, n2 = fix_ext_links(content)
        counts["ext_link"] += n2

        content, n3 = fix_excessive_blanks(content)
        counts["blanks"] += n3

        if content != original:
            modified_files.add(fpath)
            with open(fpath, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

    print(f"\nFiles modified: {len(modified_files)}")
    print(f"Fix 1 - MISSING_TH_SCOPE:  {counts['th_scope']} fixes")
    print(f"Fix 2 - EXT_LINK_ATTRS:    {counts['ext_link']} fixes")
    print(f"Fix 3 - EXCESSIVE_BLANKS:  {counts['blanks']} fixes")
    print(f"Total fixes:               {sum(counts.values())}")


if __name__ == "__main__":
    main()

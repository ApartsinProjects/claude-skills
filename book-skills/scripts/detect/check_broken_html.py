"""Scan all book HTML files for structural HTML issues.

Checks:
  1. Unclosed/mismatched tags (div, section, main, nav, header, footer, etc.)
  2. Missing </body> or </html>
  3. Missing <main> or </main>
  4. Unclosed <pre>/<code> blocks
  5. Unclosed <details>/<summary>
  6. Unclosed <table>/<tr>/<td>/<th>
  7. Mismatched <ul>/<ol>/<li>
  8. Missing closing </section> for bibliography
  9. Orphaned closing tags (more closes than opens)
  10. Missing DOCTYPE or <html> opener

Usage:
    python scripts/detect/check_broken_html.py [--verbose]
"""
import os
import re
import sys
from pathlib import Path

BOOK_ROOT = Path(__file__).resolve().parent.parent.parent

# Tags to check for balance
CHECKED_TAGS = [
    "html", "head", "body", "main", "header", "footer", "nav",
    "section", "article", "aside",
    "div", "figure", "figcaption", "blockquote",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "ul", "ol", "li", "dl", "dt", "dd",
    "details", "summary",
    "pre", "code",
    "form", "fieldset", "select", "option",
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "span", "a", "strong", "em", "sup", "sub",
]

# Self-closing tags (void elements) to ignore
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# SVG elements (self-closing in SVG context, not real HTML issues)
SVG_TAGS = {
    "svg", "g", "defs", "use", "symbol", "clippath",
    "rect", "circle", "ellipse", "line", "polyline", "polygon", "path",
    "text", "tspan", "textpath",
    "image", "pattern", "mask", "marker",
    "lineargradient", "radialgradient", "stop",
    "filter", "fegaussianblur", "feoffset", "feblend", "fecolormatrix",
    "fecomponenttransfer", "fecomposite", "feconvolvematrix",
    "fediffuselighting", "fedisplacementmap", "feflood",
    "feimage", "femerge", "femergenode", "femorphology",
    "fespecularlighting", "fetile", "feturbulence", "fedropshadow",
    "animate", "animatetransform", "animatemotion", "set",
    "foreignobject",
}

# Directories to scan
SCAN_DIRS = [
    "part-1-foundations",
    "part-2-understanding-llms",
    "part-3-working-with-llms",
    "part-4-training-adapting",
    "part-5-retrieval-conversation",
    "part-6-agentic-ai",
    "part-7-multimodal-applications",
    "part-8-evaluation-production",
    "part-9-safety-strategy",
    "part-10-frontiers",
    "appendices",
    "front-matter",
    "capstone",
]

# Regex patterns
TAG_OPEN = re.compile(r"<(\w+)(?:\s[^>]*)?>", re.DOTALL)
TAG_CLOSE = re.compile(r"</(\w+)\s*>")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL)
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL)


def strip_non_structural(html):
    """Remove comments, script, and style blocks to avoid false positives."""
    html = COMMENT_RE.sub("", html)
    html = SCRIPT_RE.sub("", html)
    html = STYLE_RE.sub("", html)
    return html


def check_tag_balance(html, filepath):
    """Check for mismatched opening/closing tags."""
    issues = []
    cleaned = strip_non_structural(html)

    opens = {}
    closes = {}

    for m in TAG_OPEN.finditer(cleaned):
        tag = m.group(1).lower()
        if tag in VOID_TAGS or tag in SVG_TAGS:
            continue
        opens[tag] = opens.get(tag, 0) + 1

    for m in TAG_CLOSE.finditer(cleaned):
        tag = m.group(1).lower()
        if tag in SVG_TAGS:
            continue
        closes[tag] = closes.get(tag, 0) + 1

    for tag in set(list(opens.keys()) + list(closes.keys())):
        if tag in VOID_TAGS or tag in SVG_TAGS:
            continue
        o = opens.get(tag, 0)
        c = closes.get(tag, 0)
        if o != c:
            diff = o - c
            if diff > 0:
                issues.append(f"  <{tag}>: {o} opens, {c} closes ({diff} unclosed)")
            else:
                issues.append(f"  </{tag}>: {c} closes, {o} opens ({-diff} orphaned closes)")

    return issues


def check_structure(html, filepath):
    """Check for missing structural elements."""
    issues = []

    if "<!DOCTYPE" not in html and "<!doctype" not in html:
        issues.append("  Missing <!DOCTYPE html>")

    if "</body>" not in html:
        issues.append("  Missing </body>")

    if "</html>" not in html:
        issues.append("  Missing </html>")

    if "<main" not in html:
        issues.append("  Missing <main> element")

    if "</main>" not in html:
        issues.append("  Missing </main> closing tag")

    return issues


def check_nesting_order(html, filepath):
    """Check for obvious nesting violations using a simple stack."""
    issues = []
    cleaned = strip_non_structural(html)

    # Only check block-level nesting for key structural tags
    structural_tags = {"main", "section", "div", "details", "table", "thead", "tbody", "ul", "ol", "dl", "figure", "blockquote", "nav", "header", "footer", "pre"}

    stack = []
    # Find all opening and closing tags
    all_tags = re.finditer(r"<(/?)(\w+)(?:\s[^>]*)?>", cleaned, re.DOTALL)

    for m in all_tags:
        is_close = m.group(1) == "/"
        tag = m.group(2).lower()

        if tag not in structural_tags or tag in VOID_TAGS:
            continue

        if not is_close:
            stack.append((tag, m.start()))
        else:
            if stack and stack[-1][0] == tag:
                stack.pop()
            elif stack:
                # Mismatch: expected to close stack[-1] but got tag
                expected = stack[-1][0]
                line_num = html[:m.start()].count("\n") + 1
                issues.append(f"  Line ~{line_num}: closing </{tag}> but expected </{expected}>")
                # Try to recover by popping if tag is further up
                found = False
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == tag:
                        stack.pop(i)
                        found = True
                        break
                if not found:
                    pass  # orphaned close tag

    if stack:
        for tag, pos in stack:
            line_num = html[:pos].count("\n") + 1
            issues.append(f"  Line ~{line_num}: unclosed <{tag}> (never closed)")

    return issues


def scan_file(filepath, verbose=False):
    """Run all checks on a single file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        return [f"  ERROR reading file: {e}"]

    all_issues = []

    # 1. Tag balance
    balance_issues = check_tag_balance(html, filepath)
    if balance_issues:
        all_issues.extend(balance_issues)

    # 2. Structure
    structure_issues = check_structure(html, filepath)
    if structure_issues:
        all_issues.extend(structure_issues)

    # 3. Nesting (only if verbose, can be noisy)
    if verbose:
        nesting_issues = check_nesting_order(html, filepath)
        if nesting_issues:
            all_issues.extend(nesting_issues)

    return all_issues


def main():
    verbose = "--verbose" in sys.argv

    all_files = []
    for scan_dir in SCAN_DIRS:
        dir_path = BOOK_ROOT / scan_dir
        if not dir_path.exists():
            continue
        for root, dirs, files in os.walk(dir_path):
            for fname in sorted(files):
                if fname.endswith(".html"):
                    all_files.append(os.path.join(root, fname))

    # Also check root-level HTML
    for fname in sorted(os.listdir(BOOK_ROOT)):
        if fname.endswith(".html"):
            all_files.append(os.path.join(str(BOOK_ROOT), fname))

    print(f"Scanning {len(all_files)} HTML files...\n")

    broken_files = 0
    total_issues = 0

    for filepath in all_files:
        rel = os.path.relpath(filepath, BOOK_ROOT).replace("\\", "/")
        issues = scan_file(filepath, verbose)

        # Filter out minor issues (p, span, a, em, strong mismatches are common in complex HTML)
        significant_issues = [i for i in issues if not any(
            t in i for t in ["<span>", "<a>", "<em>", "<strong>", "<sup>", "<sub>",
                             "</span>", "</a>", "</em>", "</strong>", "</sup>", "</sub>",
                             "<p>", "</p>"]
        )]

        if significant_issues:
            broken_files += 1
            total_issues += len(significant_issues)
            print(f"BROKEN: {rel}")
            for issue in significant_issues:
                print(issue)
            print()

    print(f"{'='*60}")
    print(f"Summary: {broken_files} files with issues out of {len(all_files)} scanned")
    print(f"Total significant issues: {total_issues}")

    if broken_files == 0:
        print("All HTML files are structurally sound!")

    return 1 if broken_files > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

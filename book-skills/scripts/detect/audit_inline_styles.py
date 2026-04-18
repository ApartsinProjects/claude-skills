"""Audit repeating elements for single-source-of-truth styling.

Finds elements that should use book.css classes but instead have:
1. Inline style= attributes on known class-based elements
2. <style> blocks that redefine book.css classes
3. One-off styling patterns that should be promoted to book.css

Reports violations grouped by element type, with file and line number.
"""
import re
from pathlib import Path
from collections import defaultdict

BOOK_ROOT = Path(r"E:\Projects\LLMCourse")

# Known class-based elements that should NEVER have inline styles
CLASS_ELEMENTS = [
    "callout", "epigraph", "prerequisites", "whats-next", "bibliography",
    "code-caption", "diagram-caption", "diagram-container", "lab",
    "chapter-nav", "chapter-header", "content",
    "pathway-link-card", "course-link-card", "pathway-grid", "course-grid",
    "pw-avatar", "pw-info", "pw-meta", "pw-who", "pw-topics",
    "psk-table", "psk-category",
    "crs-fields", "crs-field", "crs-label",
    "action", "action-skip", "action-skim", "action-focus",
    "agent-avatar-inline", "agent-card",
    "footer", "header-nav", "part-label", "chapter-label",
]

# CSS classes defined in book.css that should not be redefined in <style> blocks
BOOK_CSS_CLASSES = [
    r"\.callout\b", r"\.callout\.(big-picture|key-insight|note|warning|tip|fun-note|"
    r"practical-example|research-frontier|algorithm|exercise)",
    r"\.epigraph\b", r"\.prerequisites\b", r"\.whats-next\b",
    r"\.bibliography\b", r"\.code-caption\b", r"\.diagram-caption\b",
    r"\.lab\b", r"\.chapter-nav\b", r"\.chapter-header\b",
    r"\.content\b", r"\.pathway-link-card\b", r"\.course-link-card\b",
    r"\.header-nav\b", r"\.part-label\b", r"\.chapter-label\b",
    r"\.footer\b",
]

# Patterns that suggest repeating elements with ad-hoc styling
ADHOC_PATTERNS = [
    # Tables with inline width/color
    (r'<table[^>]+style="[^"]*"', "table with inline style"),
    # Divs with background/border inline
    (r'<div[^>]+style="[^"]*(?:background|border|padding|margin)[^"]*"', "div with layout inline style"),
    # Repeated <style> block patterns
]


def find_html_files():
    """Find all HTML files excluding vendor and deprecated dirs."""
    skip = {"vendor", "node_modules", ".git", "deprecated"}
    for f in BOOK_ROOT.rglob("*.html"):
        if not any(s in f.parts for s in skip):
            yield f


def check_inline_styles(filepath, html):
    """Find inline style= on class-based elements."""
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for cls in CLASS_ELEMENTS:
            # Match class="...cls..." with style="..."
            pattern = rf'class="[^"]*\b{re.escape(cls)}\b[^"]*"[^>]*style="([^"]*)"'
            for m in re.finditer(pattern, line):
                issues.append((filepath, i, "error",
                    f'Inline style on .{cls}: style="{m.group(1)[:60]}"'))
            # Also check style before class
            pattern2 = rf'style="([^"]*)"[^>]*class="[^"]*\b{re.escape(cls)}\b[^"]*"'
            for m in re.finditer(pattern2, line):
                issues.append((filepath, i, "error",
                    f'Inline style on .{cls}: style="{m.group(1)[:60]}"'))
    return issues


def check_style_block_overrides(filepath, html):
    """Find <style> blocks that redefine book.css classes."""
    issues = []
    style_blocks = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
    for block in style_blocks:
        for pattern in BOOK_CSS_CLASSES:
            for m in re.finditer(pattern, block):
                # Find line number
                start = html.find(block)
                line_num = html[:start + m.start()].count("\n") + 1
                issues.append((filepath, line_num, "warning",
                    f'<style> block redefines book.css class: {m.group(0)}'))
    return issues


def check_adhoc_patterns(filepath, html):
    """Find ad-hoc styling patterns that should be standardized."""
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for pattern, desc in ADHOC_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append((filepath, i, "warning", f'Ad-hoc styling: {desc}'))
    return issues


def check_repeated_style_blocks(all_style_blocks):
    """Find style definitions that appear in 3+ files (should be in book.css)."""
    # Normalize and count CSS rules across files
    rule_files = defaultdict(list)
    for filepath, block in all_style_blocks:
        # Extract individual rules (selector { ... })
        rules = re.findall(r'([.#\w][^{]+)\{([^}]+)\}', block)
        for selector, body in rules:
            selector = selector.strip()
            if selector and not selector.startswith("@"):
                rule_files[selector].append(filepath)

    issues = []
    for selector, files in rule_files.items():
        if len(files) >= 3:
            unique_files = set(str(f.relative_to(BOOK_ROOT)) for f in files)
            issues.append((files[0], 0, "warning",
                f'CSS rule "{selector}" appears in {len(files)} files '
                f'({len(unique_files)} unique); move to book.css'))
    return issues


def main():
    all_issues = []
    all_style_blocks = []
    file_count = 0

    for filepath in find_html_files():
        file_count += 1
        html = filepath.read_text(encoding="utf-8", errors="replace")

        all_issues.extend(check_inline_styles(filepath, html))
        all_issues.extend(check_style_block_overrides(filepath, html))
        all_issues.extend(check_adhoc_patterns(filepath, html))

        # Collect style blocks for cross-file analysis
        for block in re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL):
            all_style_blocks.append((filepath, block))

    # Cross-file repeated style analysis
    all_issues.extend(check_repeated_style_blocks(all_style_blocks))

    # Print results
    errors = [i for i in all_issues if i[2] == "error"]
    warnings = [i for i in all_issues if i[2] == "warning"]

    print(f"Scanned {file_count} files")
    print(f"Found {len(errors)} errors, {len(warnings)} warnings\n")

    if errors:
        print("=" * 70)
        print("ERRORS (inline styles on class-based elements)")
        print("=" * 70)
        for filepath, line, severity, msg in sorted(errors):
            rel = filepath.relative_to(BOOK_ROOT)
            print(f"  {rel}:{line}  {msg}")

    if warnings:
        print("\n" + "=" * 70)
        print("WARNINGS (style block overrides and repeated patterns)")
        print("=" * 70)

        # Group by type
        overrides = [w for w in warnings if "<style> block redefines" in w[3]]
        repeated = [w for w in warnings if "appears in" in w[3]]
        adhoc = [w for w in warnings if "Ad-hoc styling" in w[3]]

        if overrides:
            print(f"\n--- Style block overrides ({len(overrides)}) ---")
            for filepath, line, severity, msg in sorted(overrides):
                rel = filepath.relative_to(BOOK_ROOT)
                print(f"  {rel}:{line}  {msg}")

        if repeated:
            print(f"\n--- Repeated CSS rules (should be in book.css) ({len(repeated)}) ---")
            for filepath, line, severity, msg in sorted(repeated):
                print(f"  {msg}")

        if adhoc:
            print(f"\n--- Ad-hoc inline styling ({len(adhoc)}) ---")
            for filepath, line, severity, msg in sorted(adhoc):
                rel = filepath.relative_to(BOOK_ROOT)
                print(f"  {rel}:{line}  {msg}")


if __name__ == "__main__":
    main()

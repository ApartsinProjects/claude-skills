"""Comprehensive HTML quality audit for a book project.

Checks for broken cross-references, duplicate figure numbers, accessibility
issues, vendor consistency, and structural problems. Each check is a
standalone function that returns a list of Issue namedtuples.

Run with --help for usage. Uses only Python stdlib modules.
"""

import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict, namedtuple
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration constants (edit these per project)
# ---------------------------------------------------------------------------

BOOK_ROOT = Path(r"E:\Projects\LLMCourse")
BOOK_TITLE_SUFFIX = " | Mastering LLMs"
SKIP_DIRS = {"vendor", "node_modules", ".git", "deprecated", "__pycache__",
             "scripts", "generated-illustrations"}

# Priorities
P0, P1, P2, P3 = "P0", "P1", "P2", "P3"

# ---------------------------------------------------------------------------
# Issue type
# ---------------------------------------------------------------------------

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_html_files(root=BOOK_ROOT, limit_files=None):
    """Yield HTML files under root, excluding SKIP_DIRS."""
    for f in root.rglob("*.html"):
        if any(s in f.parts for s in SKIP_DIRS):
            continue
        if limit_files and f not in limit_files:
            continue
        yield f


def line_number_of(html_text, pos):
    """Return 1-based line number for a character offset."""
    return html_text[:pos].count("\n") + 1


def decode_entities(text):
    """Decode HTML entities in text."""
    return html.unescape(text)


# ---------------------------------------------------------------------------
# P0 checks
# ---------------------------------------------------------------------------


def check_broken_xref(filepath, html_text, context):
    """P0: BROKEN_XREF. Verify relative href targets exist on disk."""
    issues = []
    all_files = context.get("all_files", set())
    parent = filepath.parent

    for m in re.finditer(r'href="([^"]*)"', html_text):
        href = m.group(1).strip()
        if not href:
            continue
        # Skip anchors, absolute URLs, mailto, javascript
        if href.startswith("#") or href.startswith("http") or \
           href.startswith("mailto:") or href.startswith("javascript:"):
            continue

        # Strip fragment
        href_no_frag = href.split("#")[0]
        if not href_no_frag:
            continue

        # Resolve against file location
        target = (parent / href_no_frag).resolve()

        if target not in all_files and not target.exists():
            ln = line_number_of(html_text, m.start())
            issues.append(Issue(P0, "BROKEN_XREF", filepath, ln,
                                f'Broken link: href="{href}"'))
    return issues


def check_dup_figure_num(filepath, html_text, context):
    """P0: DUP_FIGURE_NUM. Flag duplicate Figure/Table/Listing numbers."""
    issues = []
    pattern = re.compile(r'\b(Figure|Table|Listing)\s+(\d+\.\d+(?:\.\d+)?)\b')
    seen = defaultdict(list)

    for m in pattern.finditer(html_text):
        key = f"{m.group(1)} {m.group(2)}"
        ln = line_number_of(html_text, m.start())
        seen[key].append(ln)

    for key, lines in seen.items():
        if len(lines) > 1:
            # Only flag if there are more references than expected (>2 is a dup)
            # Actually: true duplicates are when the same number labels two
            # different items. We flag any number appearing 2+ times as a
            # potential duplicate for manual review.
            issues.append(Issue(P0, "DUP_FIGURE_NUM", filepath, lines[0],
                                f'Duplicate "{key}" on lines: {", ".join(map(str, lines))}'))
    return issues


def check_svg_title_text(filepath, html_text, context):
    """P0: SVG_TITLE_TEXT. Flag <text> inside <svg> that looks like a title."""
    issues = []
    # Find SVG blocks
    for svg_m in re.finditer(r'<svg\b[^>]*>(.*?)</svg>', html_text, re.DOTALL):
        svg_content = svg_m.group(1)
        svg_start = svg_m.start()

        for text_m in re.finditer(
            r'<text\b([^>]*)>(.*?)</text>', svg_content, re.DOTALL
        ):
            attrs = text_m.group(1)
            inner = re.sub(r'<[^>]+>', '', text_m.group(2)).strip()
            decoded = decode_entities(inner)
            word_count = len(decoded.split())

            if word_count <= 3:
                continue

            # Check y attribute
            y_match = re.search(r'\by="([^"]*)"', attrs)
            y_val = float(y_match.group(1)) if y_match else 999

            # Check font-size
            fs_match = re.search(r'font-size[:\s="]+(\d+(?:\.\d+)?)', attrs)
            fs_val = float(fs_match.group(1)) if fs_match else 0

            # Check font-weight
            bold = bool(re.search(r'font-weight[:\s="]+bold', attrs, re.IGNORECASE))

            is_title = y_val < 45 and (fs_val >= 13 or bold)

            if is_title:
                ln = line_number_of(html_text, svg_start + text_m.start())
                snippet = decoded[:50]
                issues.append(Issue(P0, "SVG_TITLE_TEXT", filepath, ln,
                                    f'SVG title text (redundant with caption): "{snippet}"'))
    return issues


# ---------------------------------------------------------------------------
# P1 checks
# ---------------------------------------------------------------------------


def check_unused_vendor(filepath, html_text, context):
    """P1: UNUSED_VENDOR. KaTeX loaded but no math; Prism loaded but no code."""
    issues = []

    has_katex = bool(re.search(r'katex', html_text, re.IGNORECASE))
    has_math = bool(re.search(r'\$\$|\\\(|\\\[', html_text))
    # Also check for katex class usage
    has_math = has_math or bool(re.search(r'class="[^"]*katex', html_text))

    if has_katex and not has_math:
        ln = 1
        m = re.search(r'katex', html_text, re.IGNORECASE)
        if m:
            ln = line_number_of(html_text, m.start())
        issues.append(Issue(P1, "UNUSED_VENDOR", filepath, ln,
                            "KaTeX loaded but no math content found"))

    has_prism = bool(re.search(r'prism', html_text, re.IGNORECASE))
    has_code = bool(re.search(r'<pre[^>]*>\s*<code', html_text))

    if has_prism and not has_code:
        ln = 1
        m = re.search(r'prism', html_text, re.IGNORECASE)
        if m:
            ln = line_number_of(html_text, m.start())
        issues.append(Issue(P1, "UNUSED_VENDOR", filepath, ln,
                            "Prism loaded but no <pre><code> blocks found"))

    return issues


def check_missing_meta_desc(filepath, html_text, context):
    """P1: MISSING_META_DESC. No <meta name='description'>."""
    issues = []
    if not re.search(r'<meta\s+name="description"', html_text, re.IGNORECASE):
        issues.append(Issue(P1, "MISSING_META_DESC", filepath, 1,
                            "Missing <meta name=\"description\"> tag"))
    return issues


def check_title_format(filepath, html_text, context):
    """P1: TITLE_FORMAT. <title> not ending with book name suffix."""
    issues = []
    m = re.search(r'<title>(.*?)</title>', html_text, re.DOTALL)
    if m:
        title = m.group(1).strip()
        if not title.endswith(BOOK_TITLE_SUFFIX.strip()):
            ln = line_number_of(html_text, m.start())
            issues.append(Issue(P1, "TITLE_FORMAT", filepath, ln,
                                f'Title "{title[:60]}" does not end with '
                                f'"{BOOK_TITLE_SUFFIX.strip()}"'))
    else:
        issues.append(Issue(P1, "TITLE_FORMAT", filepath, 1,
                            "No <title> element found"))
    return issues


def check_footer_placement(filepath, html_text, context):
    """P1: FOOTER_PLACEMENT. Collect footer placement for cross-file check.

    Returns issues only during the cross-file phase (see run_cross_file_checks).
    Here we just record the pattern into context.
    """
    # We detect whether <footer> is inside <main> or outside it.
    # Strategy: check if </main> appears before <footer>
    main_close = html_text.find("</main>")
    footer_open = html_text.find("<footer")

    if footer_open == -1:
        return []

    placement = "outside" if (main_close != -1 and footer_open > main_close) else "inside"

    fp_data = context.setdefault("footer_placements", {})
    fp_data[str(filepath)] = placement
    return []


def check_dup_code_comment(filepath, html_text, context):
    """P1: DUP_CODE_COMMENT. Identical comments (>15 chars) in 2+ code blocks."""
    issues = []

    # Extract code blocks
    code_blocks = re.findall(r'<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>',
                             html_text, re.DOTALL)
    if len(code_blocks) < 2:
        return issues

    # Collect comments from each block
    comment_patterns = [
        re.compile(r'//\s*(.{16,})'),      # C-style single line
        re.compile(r'#\s*(.{16,})'),        # Python/shell style
        re.compile(r'/\*\s*(.{16,?})\s*\*/'),  # C-style block (non-greedy)
    ]

    all_comments = Counter()
    for block in code_blocks:
        decoded_block = decode_entities(block)
        block_comments = set()
        for pat in comment_patterns:
            for cm in pat.finditer(decoded_block):
                comment_text = cm.group(1).strip()
                if len(comment_text) > 15:
                    block_comments.add(comment_text)
        for c in block_comments:
            all_comments[c] += 1

    for comment, count in all_comments.items():
        if count >= 2:
            issues.append(Issue(P1, "DUP_CODE_COMMENT", filepath, 0,
                                f'Identical comment in {count} code blocks: '
                                f'"{comment[:60]}"'))
    return issues


# ---------------------------------------------------------------------------
# P2 checks
# ---------------------------------------------------------------------------


def check_missing_img_dims(filepath, html_text, context):
    """P2: MISSING_IMG_DIMS. <img> without width or height."""
    issues = []
    for m in re.finditer(r'<img\b([^>]*)/?>', html_text, re.DOTALL):
        attrs = m.group(1)
        has_width = bool(re.search(r'\bwidth\s*=', attrs))
        has_height = bool(re.search(r'\bheight\s*=', attrs))
        if not has_width or not has_height:
            ln = line_number_of(html_text, m.start())
            src = ""
            src_m = re.search(r'src="([^"]*)"', attrs)
            if src_m:
                src = src_m.group(1)
            missing = []
            if not has_width:
                missing.append("width")
            if not has_height:
                missing.append("height")
            issues.append(Issue(P2, "MISSING_IMG_DIMS", filepath, ln,
                                f'<img> missing {", ".join(missing)}: {src[:60]}'))
    return issues


def check_missing_th_scope(filepath, html_text, context):
    """P2: MISSING_TH_SCOPE. <th> without scope attribute."""
    issues = []
    for m in re.finditer(r'<th\b([^>]*)>', html_text):
        attrs = m.group(1)
        if not re.search(r'\bscope\s*=', attrs):
            ln = line_number_of(html_text, m.start())
            issues.append(Issue(P2, "MISSING_TH_SCOPE", filepath, ln,
                                "<th> missing scope attribute"))
    return issues


def check_orphan_content(filepath, html_text, context):
    """P2: ORPHAN_CONTENT. Non-whitespace between </header> and <main>."""
    issues = []
    m = re.search(r'</header>(.*?)<main\b', html_text, re.DOTALL)
    if m:
        between = m.group(1)
        # Strip HTML comments and whitespace
        cleaned = re.sub(r'<!--.*?-->', '', between, flags=re.DOTALL)
        cleaned = cleaned.strip()
        if cleaned:
            ln = line_number_of(html_text, m.start())
            snippet = cleaned[:60].replace("\n", " ")
            issues.append(Issue(P2, "ORPHAN_CONTENT", filepath, ln,
                                f'Content between </header> and <main>: "{snippet}"'))
    return issues


def check_generic_svg_label(filepath, html_text, context):
    """P2: GENERIC_SVG_LABEL. SVG aria-label matching non-descriptive patterns."""
    issues = []
    generic_patterns = [
        re.compile(r'^Diagram\s*\d*$', re.IGNORECASE),
        re.compile(r'^Figure\s*\d*$', re.IGNORECASE),
        re.compile(r'^Chart\s*\d*$', re.IGNORECASE),
        re.compile(r'^Image\s*\d*$', re.IGNORECASE),
        re.compile(r'^Illustration\s*\d*$', re.IGNORECASE),
        re.compile(r'^SVG\s*\d*$', re.IGNORECASE),
        re.compile(r'^Graphic\s*\d*$', re.IGNORECASE),
    ]

    for m in re.finditer(r'<svg\b[^>]*aria-label="([^"]*)"', html_text):
        label = m.group(1).strip()
        for pat in generic_patterns:
            if pat.match(label):
                ln = line_number_of(html_text, m.start())
                issues.append(Issue(P2, "GENERIC_SVG_LABEL", filepath, ln,
                                    f'Non-descriptive SVG aria-label: "{label}"'))
                break
    return issues


def check_svg_text_overflow(filepath, html_text, context):
    """P2: SVG_TEXT_OVERFLOW. Text in SVG shapes wider than the shape."""
    issues = []

    for svg_m in re.finditer(r'<svg\b[^>]*>(.*?)</svg>', html_text, re.DOTALL):
        svg_content = svg_m.group(1)
        svg_start = svg_m.start()

        # Collect shapes with positions and sizes
        shapes = []

        # Circles: cx, cy, r
        for cm in re.finditer(r'<circle\b([^>]*)/?>', svg_content):
            attrs = cm.group(1)
            cx_m = re.search(r'\bcx="([^"]*)"', attrs)
            cy_m = re.search(r'\bcy="([^"]*)"', attrs)
            r_m = re.search(r'\br="([^"]*)"', attrs)
            if cx_m and cy_m and r_m:
                try:
                    cx = float(cx_m.group(1))
                    cy = float(cy_m.group(1))
                    r = float(r_m.group(1))
                    shapes.append(("circle", cx - r, cy - r, 2 * r, 2 * r,
                                   cm.start(), cx, cy))
                except ValueError:
                    pass

        # Rects: x, y, width, height
        for rm in re.finditer(r'<rect\b([^>]*)/?>', svg_content):
            attrs = rm.group(1)
            x_m = re.search(r'\bx="([^"]*)"', attrs)
            y_m = re.search(r'\by="([^"]*)"', attrs)
            w_m = re.search(r'\bwidth="([^"]*)"', attrs)
            h_m = re.search(r'\bheight="([^"]*)"', attrs)
            if w_m and h_m:
                try:
                    x = float(x_m.group(1)) if x_m else 0
                    y = float(y_m.group(1)) if y_m else 0
                    w = float(w_m.group(1))
                    h = float(h_m.group(1))
                    shapes.append(("rect", x, y, w, h, rm.start(),
                                   x + w / 2, y + h / 2))
                except ValueError:
                    pass

        # Check text elements against nearby shapes
        for text_m in re.finditer(
            r'<text\b([^>]*)>(.*?)</text>', svg_content, re.DOTALL
        ):
            text_attrs = text_m.group(1)
            inner = re.sub(r'<[^>]+>', '', text_m.group(2)).strip()
            decoded = decode_entities(inner)

            if not decoded:
                continue

            # Get text position
            tx_m = re.search(r'\bx="([^"]*)"', text_attrs)
            ty_m = re.search(r'\by="([^"]*)"', text_attrs)
            if not tx_m or not ty_m:
                continue
            try:
                tx = float(tx_m.group(1))
                ty = float(ty_m.group(1))
            except ValueError:
                continue

            # Get font-size
            fs_m = re.search(r'font-size[:\s="]+(\d+(?:\.\d+)?)', text_attrs)
            fs = float(fs_m.group(1)) if fs_m else 14

            # Determine font type
            is_mono = bool(re.search(
                r'font-family[:\s="]+[^"]*mono', text_attrs, re.IGNORECASE
            ))
            char_width_factor = 0.6 if is_mono else 0.55

            text_width = len(decoded) * fs * char_width_factor

            # Find the closest enclosing shape
            for shape_type, sx, sy, sw, sh, s_pos, scx, scy in shapes:
                # Check if text center is roughly within shape bounds
                if abs(tx - scx) < sw and abs(ty - scy) < sh:
                    container_width = sw
                    if shape_type == "circle":
                        # Effective width at text y within circle
                        r = sw / 2
                        dy = abs(ty - scy)
                        if dy < r:
                            container_width = 2 * (r * r - dy * dy) ** 0.5
                        else:
                            container_width = 0

                    if text_width > container_width and container_width > 0:
                        ln = line_number_of(html_text,
                                            svg_start + text_m.start())
                        issues.append(Issue(
                            P2, "SVG_TEXT_OVERFLOW", filepath, ln,
                            f'Text "{decoded[:40]}" (est. {text_width:.0f}px) '
                            f'overflows {shape_type} ({container_width:.0f}px wide)'
                        ))
                    break  # Only check the closest match

    return issues


# ---------------------------------------------------------------------------
# P3 checks
# ---------------------------------------------------------------------------


def check_unescaped_amp(filepath, html_text, context):
    """P3: UNESCAPED_AMP. Bare & outside code/pre/script/svg."""
    issues = []

    # Remove content inside tags we want to skip
    # Replace <pre>...</pre>, <code>...</code>, <script>...</script>,
    # <svg>...</svg> with placeholder
    cleaned = html_text
    for tag in ("pre", "code", "script", "svg", "style"):
        cleaned = re.sub(
            rf'<{tag}\b[^>]*>.*?</{tag}>',
            f' __{tag}_block__ ',
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Also remove HTML tags themselves (we only want text content)
    text_only = re.sub(r'<[^>]+>', ' ', cleaned)

    # Find bare & not followed by a valid entity pattern
    # Valid: &word; or &#digits; or &#xhex;
    for m in re.finditer(r'&(?![a-zA-Z0-9#][a-zA-Z0-9]*;)', text_only):
        # Map position back to original (approximate since we modified the string)
        # For accuracy, search in the original around the same offset
        ln = line_number_of(text_only, m.start())
        issues.append(Issue(P3, "UNESCAPED_AMP", filepath, ln,
                            "Unescaped & (should be &amp;)"))

    return issues


def check_missing_skip_link(filepath, html_text, context):
    """P3: MISSING_SKIP_LINK. No skip-to-content link near top of body."""
    issues = []
    body_m = re.search(r'<body\b[^>]*>(.*)', html_text, re.DOTALL)
    if body_m:
        # Check first 2000 chars after <body>
        top = body_m.group(1)[:2000]
        if not re.search(r'skip.*(?:content|main|nav)', top, re.IGNORECASE):
            ln = line_number_of(html_text, body_m.start())
            issues.append(Issue(P3, "MISSING_SKIP_LINK", filepath, ln,
                                "No skip-to-content link near top of <body>"))
    return issues


def check_vendor_path_prefix(filepath, html_text, context):
    """P3: VENDOR_PATH_PREFIX. Collect vendor path prefixes for cross-file check."""
    # Collect all vendor references and their prefix style
    prefixes = context.setdefault("vendor_prefixes", defaultdict(list))

    for m in re.finditer(r'(?:href|src)="((?:\.\./)*(?:\./)?vendor/[^"]*)"', html_text):
        ref = m.group(1)
        # Extract prefix portion before "vendor/"
        idx = ref.index("vendor/")
        prefix = ref[:idx] if idx > 0 else "(none)"
        prefixes[prefix].append((filepath, line_number_of(html_text, m.start())))

    return []


# ---------------------------------------------------------------------------
# Cross-file checks (run after all per-file passes)
# ---------------------------------------------------------------------------


def run_cross_file_checks(context):
    """Run checks that require data from all files."""
    issues = []

    # FOOTER_PLACEMENT: flag minority pattern
    fp_data = context.get("footer_placements", {})
    if fp_data:
        inside_count = sum(1 for v in fp_data.values() if v == "inside")
        outside_count = sum(1 for v in fp_data.values() if v == "outside")

        if inside_count > 0 and outside_count > 0:
            # Flag minority
            if inside_count <= outside_count:
                minority = "inside"
                majority = "outside"
            else:
                minority = "outside"
                majority = "inside"

            minority_files = [fp for fp, v in fp_data.items() if v == minority]
            for fp in minority_files:
                issues.append(Issue(
                    P1, "FOOTER_PLACEMENT", Path(fp), 0,
                    f'Footer is {minority} <main> (majority is {majority}; '
                    f'{len(minority_files)} files in minority vs '
                    f'{len(fp_data) - len(minority_files)} in majority)'
                ))

    # VENDOR_PATH_PREFIX: flag inconsistency
    vp_data = context.get("vendor_prefixes", {})
    if len(vp_data) > 1:
        # Find the most common prefix
        prefix_counts = {p: len(files) for p, files in vp_data.items()}
        majority_prefix = max(prefix_counts, key=prefix_counts.get)

        for prefix, file_lines in vp_data.items():
            if prefix != majority_prefix:
                for fp, ln in file_lines:
                    issues.append(Issue(
                        P3, "VENDOR_PATH_PREFIX", fp, ln,
                        f'Vendor prefix "{prefix}" differs from majority '
                        f'"{majority_prefix}" ({prefix_counts[majority_prefix]} files)'
                    ))

    return issues


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

PER_FILE_CHECKS = [
    (P0, "BROKEN_XREF",       check_broken_xref),
    (P0, "DUP_FIGURE_NUM",    check_dup_figure_num),
    (P0, "SVG_TITLE_TEXT",     check_svg_title_text),
    (P1, "UNUSED_VENDOR",     check_unused_vendor),
    (P1, "MISSING_META_DESC", check_missing_meta_desc),
    (P1, "TITLE_FORMAT",      check_title_format),
    (P1, "FOOTER_PLACEMENT",  check_footer_placement),
    (P1, "DUP_CODE_COMMENT",  check_dup_code_comment),
    (P2, "MISSING_IMG_DIMS",  check_missing_img_dims),
    (P2, "MISSING_TH_SCOPE",  check_missing_th_scope),
    (P2, "ORPHAN_CONTENT",    check_orphan_content),
    (P2, "GENERIC_SVG_LABEL", check_generic_svg_label),
    (P2, "SVG_TEXT_OVERFLOW",  check_svg_text_overflow),
    (P3, "UNESCAPED_AMP",     check_unescaped_amp),
    (P3, "MISSING_SKIP_LINK", check_missing_skip_link),
    (P3, "VENDOR_PATH_PREFIX", check_vendor_path_prefix),
]

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_issue_text(issue, root=BOOK_ROOT):
    """Format a single issue for human-readable output."""
    try:
        rel = issue.filepath.relative_to(root)
    except ValueError:
        rel = issue.filepath
    loc = f"{rel}:{issue.line}" if issue.line else str(rel)
    return f"  [{issue.check_id}] {loc}  {issue.message}"


def format_issue_json(issue, root=BOOK_ROOT):
    """Format a single issue as a JSON-serializable dict."""
    try:
        rel = str(issue.filepath.relative_to(root))
    except ValueError:
        rel = str(issue.filepath)
    return {
        "priority": issue.priority,
        "check_id": issue.check_id,
        "file": rel,
        "line": issue.line,
        "message": issue.message,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="HTML quality audit for book projects."
    )
    parser.add_argument(
        "--priority", choices=["P0", "P1", "P2", "P3"], default=None,
        help="Show only issues at this priority level."
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON."
    )
    parser.add_argument(
        "--files", nargs="+", default=None,
        help="Limit scan to specific files (relative or absolute paths)."
    )
    args = parser.parse_args()

    # Resolve file limits
    limit_files = None
    if args.files:
        limit_files = set()
        for f in args.files:
            p = Path(f)
            if not p.is_absolute():
                p = BOOK_ROOT / p
            limit_files.add(p.resolve())

    # Build set of all HTML files for cross-reference checking
    all_html_files = set()
    for f in find_html_files(BOOK_ROOT):
        all_html_files.add(f.resolve())

    context = {
        "all_files": all_html_files,
    }

    all_issues = []
    file_count = 0

    # Determine which priorities to run
    if args.priority:
        active_priorities = {args.priority}
    else:
        active_priorities = {P0, P1, P2, P3}

    # Per-file pass
    for filepath in find_html_files(BOOK_ROOT, limit_files):
        file_count += 1
        try:
            html_text = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            all_issues.append(Issue(P0, "READ_ERROR", filepath, 0, str(e)))
            continue

        for priority, check_id, check_fn in PER_FILE_CHECKS:
            if priority in active_priorities:
                try:
                    results = check_fn(filepath, html_text, context)
                    all_issues.extend(results)
                except Exception as e:
                    all_issues.append(Issue(
                        P0, "CHECK_ERROR", filepath, 0,
                        f"{check_id} raised {type(e).__name__}: {e}"
                    ))

    # Cross-file checks
    cross_issues = run_cross_file_checks(context)
    for issue in cross_issues:
        if issue.priority in active_priorities:
            all_issues.append(issue)

    # Filter by priority if requested
    if args.priority:
        all_issues = [i for i in all_issues if i.priority == args.priority]

    # Sort: by priority, then check_id, then filepath, then line
    priority_order = {P0: 0, P1: 1, P2: 2, P3: 3}
    all_issues.sort(key=lambda i: (
        priority_order.get(i.priority, 9),
        i.check_id,
        str(i.filepath),
        i.line,
    ))

    # Count by priority
    counts = Counter(i.priority for i in all_issues)

    # Output
    if args.json_output:
        output = {
            "scanned_files": file_count,
            "summary": {p: counts.get(p, 0) for p in [P0, P1, P2, P3]},
            "issues": [format_issue_json(i) for i in all_issues],
        }
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        # Group by priority, then by check_id
        current_priority = None
        current_check = None
        for issue in all_issues:
            if issue.priority != current_priority:
                current_priority = issue.priority
                current_check = None
                print(f"\n{'=' * 70}")
                print(f"  {current_priority} issues")
                print(f"{'=' * 70}")

            if issue.check_id != current_check:
                current_check = issue.check_id
                check_issues = [i for i in all_issues
                                if i.priority == current_priority
                                and i.check_id == current_check]
                print(f"\n  [{current_check}] ({len(check_issues)} issues)")

            print(format_issue_text(issue))

        # Summary
        print(f"\n{'=' * 70}")
        print(f"Scanned {file_count} files. Found "
              f"{counts.get(P0, 0)} P0, {counts.get(P1, 0)} P1, "
              f"{counts.get(P2, 0)} P2, {counts.get(P3, 0)} P3 issues.")


if __name__ == "__main__":
    # Ensure stdout handles Unicode on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8",
                          errors="replace", buffering=1)
    main()

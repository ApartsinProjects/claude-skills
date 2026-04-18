"""Detect common math rendering issues in HTML files using KaTeX.

Checks for:
1. PROSE_IN_MATH_BLOCK: $$...$$ blocks containing English prose (>3 alphabetic
   words not typical of LaTeX commands).
2. BARE_MATH_SPAN: <span class="math"> without $...$ delimiters inside.
3. HTML_ENTITY_IN_MATH: HTML entities inside $...$ or <span class="math"> that
   should be LaTeX equivalents.
4. ORPHANED_MATH: LaTeX-like content outside any math container.
5. BROKEN_MATH_BLOCK: <div class="math-block"> with missing or malformed $$
   delimiters.
6. UNCLOSED_DELIMITER: Mismatched $ delimiters within a line (odd count after
   excluding $$).
"""

import re
import os
import json
import sys
from collections import namedtuple
from pathlib import Path

PRIORITY = "P2"
CHECK_ID = "MATH_RENDERING"
DESCRIPTION = "Math rendering issue: KaTeX content may not display correctly"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# ---------------------------------------------------------------------------
# Shared patterns
# ---------------------------------------------------------------------------

# LaTeX commands that are normal in math mode
LATEX_COMMANDS = {
    "text", "textbf", "textit", "mathrm", "mathbf", "mathcal", "mathbb",
    "operatorname", "frac", "sqrt", "sum", "prod", "int", "log", "exp",
    "sin", "cos", "tan", "lim", "sup", "inf", "max", "min", "arg",
    "det", "dim", "gcd", "Pr", "binom", "choose", "left", "right",
    "bar", "hat", "vec", "dot", "ddot", "tilde", "overline", "underline",
    "overbrace", "underbrace", "begin", "end", "quad", "qquad",
    "cdot", "cdots", "ldots", "times", "div", "pm", "mp", "leq", "geq",
    "neq", "approx", "equiv", "sim", "propto", "in", "notin", "subset",
    "supset", "cup", "cap", "forall", "exists", "nabla", "partial",
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma",
    "tau", "upsilon", "phi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi",
    "Psi", "Omega", "infty", "to", "rightarrow", "leftarrow",
    "Rightarrow", "Leftarrow", "mapsto", "iff",
    "RoPE", "softmax", "sigmoid", "relu", "tanh",
}

# Words that are definitely prose (not math variable names)
PROSE_WORDS_RE = re.compile(
    r'\b('
    r'the|this|that|these|those|'
    r'is|are|was|were|has|have|had|'
    r'and|but|or|not|nor|'
    r'for|from|with|into|onto|upon|'
    r'where|which|when|while|who|what|how|why|'
    r'also|then|thus|hence|therefore|however|'
    r'typically|often|usually|sometimes|always|never|'
    r'should|could|would|can|will|may|might|shall|'
    r'each|every|some|any|all|most|many|few|'
    r'because|since|although|though|unless|until|'
    r'between|during|before|after|above|below|'
    r'model|models|output|input|layer|layers|'
    r'represents?|compute[sd]?|calculate[sd]?|determines?|'
    r'describes?|defines?|produces?|returns?'
    r')\b', re.IGNORECASE
)

# HTML entities that should be LaTeX in math context
ENTITY_MAP = {
    "&#773;": r"\bar{}",
    "&#x305;": r"\bar{}",
    "&times;": r"\times",
    "&gt;": ">",
    "&lt;": "<",
    "&le;": r"\leq",
    "&ge;": r"\geq",
    "&ne;": r"\neq",
    "&plusmn;": r"\pm",
    "&minus;": "-",
    "&sdot;": r"\cdot",
    "&middot;": r"\cdot",
    "&sum;": r"\sum",
    "&prod;": r"\prod",
    "&radic;": r"\sqrt{}",
    "&infin;": r"\infty",
    "&part;": r"\partial",
    "&nabla;": r"\nabla",
    "&isin;": r"\in",
    "&notin;": r"\notin",
    "&sub;": r"\subset",
    "&sup;": r"\supset",
    "&forall;": r"\forall",
    "&exist;": r"\exists",
    "&alpha;": r"\alpha",
    "&beta;": r"\beta",
    "&gamma;": r"\gamma",
    "&delta;": r"\delta",
    "&theta;": r"\theta",
    "&lambda;": r"\lambda",
    "&pi;": r"\pi",
    "&sigma;": r"\sigma",
    "&phi;": r"\phi",
    "&omega;": r"\omega",
}

ENTITY_RE = re.compile(
    r'(&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z]+);)'
)

# HTML entities that browsers decode to valid math characters; skip these
# since KaTeX will see the decoded form and render them correctly.
BROWSER_DECODED_ENTITIES = {"&lt;", "&gt;", "&amp;"}

# Patterns that suggest LaTeX math content (must be strong signals)
LATEX_LIKE_RE = re.compile(
    r'(?:'
    r'\\[a-zA-Z]{2,}'       # backslash commands like \frac, \sum
    r'|[a-zA-Z]_\{[^}]+\}'  # subscripts like x_{i}
    r'|[a-zA-Z]\^\{[^}]+\}' # superscripts like x^{2}
    r'|\^\{[^}]+\}'         # superscript like ^{2}
    r')'
)

# Display math block
DISPLAY_MATH_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)

# Inline math
INLINE_MATH_RE = re.compile(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)')

# Math span
MATH_SPAN_RE = re.compile(
    r'<span\s+class="math">(.*?)</span>', re.DOTALL
)

# Math block div
MATH_BLOCK_DIV_RE = re.compile(
    r'<div\s+class="math-block">(.*?)</div>', re.DOTALL
)


def _line_num(html, pos):
    """Return 1-based line number for a character position."""
    return html[:pos].count("\n") + 1


def _snippet(text, max_len=80):
    """Clean and truncate text for display."""
    s = text.strip().replace("\n", " ")
    s = re.sub(r'\s+', ' ', s)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def _strip_latex_commands(text):
    """Remove LaTeX commands and \\text{...} blocks to isolate prose words."""
    # Remove \text{...}, \textbf{...}, \operatorname{...}, \mathrm{...}
    cleaned = re.sub(r'\\(?:text|textbf|textit|mathrm|operatorname)\{[^}]*\}', '', text)
    # Remove all \command sequences
    cleaned = re.sub(r'\\[a-zA-Z]+', '', cleaned)
    # Remove math operators and symbols
    cleaned = re.sub(r'[_^{}()|/\[\].,;:=+*<>\\0-9\-]', ' ', cleaned)
    # Remove HTML entities
    cleaned = re.sub(r'&[A-Za-z#0-9x]+;', ' ', cleaned)
    return cleaned


def _is_inside_html_tag(html, pos):
    """Check if position is inside an HTML tag (between < and >)."""
    # Look backward for < or >
    i = pos - 1
    while i >= 0:
        if html[i] == '>':
            return False
        if html[i] == '<':
            return True
        i -= 1
    return False


def _is_inside_code_block(html, pos):
    """Check if position is inside <pre>, <code>, <script>, code-caption, or code-output."""
    before = html[:pos]
    for tag in ('pre', 'code', 'script'):
        last_open = before.rfind(f'<{tag}')
        last_close = before.rfind(f'</{tag}')
        if last_open > last_close:
            return True
    # Also check for code-caption divs
    last_caption_open = before.rfind('<div class="code-caption">')
    last_caption_close = before.rfind('</div>')
    if last_caption_open > -1 and last_caption_open > last_caption_close:
        return True
    # Also check for code-output divs
    last_output_open = before.rfind('<div class="code-output">')
    last_output_close = before.rfind('</div>')
    if last_output_open > -1 and last_output_open > last_output_close:
        return True
    return False


def _build_math_spans(html):
    """Pre-compute all math container spans as (start, end) tuples."""
    spans = []

    # $$...$$ display math
    for m in DISPLAY_MATH_RE.finditer(html):
        spans.append((m.start(), m.end()))

    # $...$ inline math: process line by line and find balanced $ pairs.
    # This avoids false matches across lines and handles \$ (escaped dollar)
    # inside math expressions correctly.
    offset = 0
    for line in html.split('\n'):
        # Strip escaped dollars for matching purposes, but track positions
        # Work on the raw line: find $ positions that are not preceded by \
        dollar_positions = []
        i = 0
        while i < len(line):
            if line[i] == '$':
                # Check for $$ (display math, handled separately)
                if i + 1 < len(line) and line[i + 1] == '$':
                    i += 2
                    continue
                # Check for \$ (escaped dollar, not a delimiter)
                if i > 0 and line[i - 1] == '\\':
                    i += 1
                    continue
                dollar_positions.append(i)
            i += 1
        # Pair up consecutive dollar signs as inline math spans
        for j in range(0, len(dollar_positions) - 1, 2):
            start = offset + dollar_positions[j]
            end = offset + dollar_positions[j + 1] + 1
            spans.append((start, end))
        offset += len(line) + 1  # +1 for newline

    # <span class="math">...</span>
    for m in MATH_SPAN_RE.finditer(html):
        spans.append((m.start(), m.end()))

    # <div class="math-block">...</div>
    for m in MATH_BLOCK_DIV_RE.finditer(html):
        spans.append((m.start(), m.end()))

    spans.sort()
    return spans


def _is_inside_math_container(html, pos, math_spans=None):
    """Check if position is inside a $, $$, span.math, or div.math-block."""
    if math_spans is not None:
        for start, end in math_spans:
            if start > pos:
                break
            if start <= pos < end:
                return True
        return False

    # Fallback: build spans on the fly (used if caller does not pass spans)
    return _is_inside_math_container(html, pos, _build_math_spans(html))


def check_prose_in_math_block(html):
    """Check 1: $$...$$ blocks containing English prose."""
    issues = []
    for m in DISPLAY_MATH_RE.finditer(html):
        block = m.group(1)
        cleaned = _strip_latex_commands(block)
        words = [w for w in cleaned.split() if len(w) >= 3 and w.isalpha()]
        # Filter to actual prose words (not variable names like "pos", "dim")
        prose_hits = list(PROSE_WORDS_RE.finditer(cleaned))
        if len(prose_hits) > 3:
            line = _line_num(html, m.start())
            sample = [h.group(0) for h in prose_hits[:4]]
            issues.append(Issue(
                PRIORITY, CHECK_ID, None, line,
                f'PROSE_IN_MATH_BLOCK: $$...$$ contains prose words: '
                f'"{", ".join(sample)}..." -- {_snippet(block)}'
            ))
    return issues


def check_bare_math_span(html):
    """Check 2: <span class="math"> without $ delimiters."""
    issues = []
    for m in MATH_SPAN_RE.finditer(html):
        content = m.group(1).strip()
        # If content contains $ delimiters, it is fine
        if '$' in content:
            continue
        # If it is empty, skip
        if not content:
            continue
        # This span will render as plain text, not math
        line = _line_num(html, m.start())
        issues.append(Issue(
            PRIORITY, CHECK_ID, None, line,
            f'BARE_MATH_SPAN: <span class="math">{_snippet(content, 40)}</span> '
            f'has no $...$ delimiters, will render as plain text'
        ))
    return issues


def check_html_entity_in_math(html):
    """Check 3: HTML entities inside math contexts."""
    issues = []

    # Check inside $...$ inline math
    for m in INLINE_MATH_RE.finditer(html):
        content = m.group(1)
        for ent_m in ENTITY_RE.finditer(content):
            entity = ent_m.group(1)
            if entity in BROWSER_DECODED_ENTITIES:
                continue
            if entity in ENTITY_MAP:
                line = _line_num(html, m.start())
                issues.append(Issue(
                    PRIORITY, CHECK_ID, None, line,
                    f'HTML_ENTITY_IN_MATH: "{entity}" inside $...$ should be '
                    f'LaTeX "{ENTITY_MAP[entity]}"'
                ))

    # Check inside $$...$$ display math
    for m in DISPLAY_MATH_RE.finditer(html):
        content = m.group(1)
        for ent_m in ENTITY_RE.finditer(content):
            entity = ent_m.group(1)
            if entity in BROWSER_DECODED_ENTITIES:
                continue
            if entity in ENTITY_MAP:
                line = _line_num(html, m.start())
                issues.append(Issue(
                    PRIORITY, CHECK_ID, None, line,
                    f'HTML_ENTITY_IN_MATH: "{entity}" inside $$...$$ should be '
                    f'LaTeX "{ENTITY_MAP[entity]}"'
                ))

    # Check inside <span class="math"> (whether or not it has $)
    for m in MATH_SPAN_RE.finditer(html):
        content = m.group(1)
        for ent_m in ENTITY_RE.finditer(content):
            entity = ent_m.group(1)
            if entity in BROWSER_DECODED_ENTITIES:
                continue
            if entity in ENTITY_MAP:
                line = _line_num(html, m.start())
                issues.append(Issue(
                    PRIORITY, CHECK_ID, None, line,
                    f'HTML_ENTITY_IN_MATH: "{entity}" inside <span class="math"> '
                    f'should be LaTeX "{ENTITY_MAP[entity]}"'
                ))

    return issues


def check_orphaned_math(html):
    """Check 4: LaTeX-like patterns outside any math container."""
    issues = []
    seen_lines = set()
    math_spans = _build_math_spans(html)

    for m in LATEX_LIKE_RE.finditer(html):
        pos = m.start()
        line = _line_num(html, pos)

        # Only report one orphan per line to reduce noise
        if line in seen_lines:
            continue

        # Skip if inside HTML tag attributes
        if _is_inside_html_tag(html, pos):
            continue

        # Skip if inside code block or code-caption
        if _is_inside_code_block(html, pos):
            continue

        # Skip if already inside a math container
        if _is_inside_math_container(html, pos, math_spans):
            continue

        # Skip if inside an HTML comment
        before = html[:pos]
        last_comment_open = before.rfind('<!--')
        last_comment_close = before.rfind('-->')
        if last_comment_open > last_comment_close:
            continue

        # Skip if inside <details> answer blocks (often use informal notation)
        last_details_open = before.rfind('<details')
        last_details_close = before.rfind('</details')
        if last_details_open > last_details_close:
            continue

        # Get the line text for snippet
        line_start = html.rfind('\n', 0, pos) + 1
        line_end = html.find('\n', pos)
        if line_end == -1:
            line_end = len(html)
        line_text = html[line_start:line_end]

        seen_lines.add(line)
        issues.append(Issue(
            PRIORITY, CHECK_ID, None, line,
            f'ORPHANED_MATH: LaTeX-like "{m.group()}" outside math container '
            f'-- {_snippet(line_text)}'
        ))

    return issues


def check_broken_math_block(html):
    """Check 5: <div class="math-block"> with missing/malformed $$ delimiters."""
    issues = []
    for m in MATH_BLOCK_DIV_RE.finditer(html):
        content = m.group(1).strip()
        line = _line_num(html, m.start())

        if not content:
            issues.append(Issue(
                PRIORITY, CHECK_ID, None, line,
                'BROKEN_MATH_BLOCK: <div class="math-block"> is empty'
            ))
            continue

        # Count $$ occurrences
        dd_count = content.count('$$')
        if dd_count == 0:
            # No $$ at all
            issues.append(Issue(
                PRIORITY, CHECK_ID, None, line,
                f'BROKEN_MATH_BLOCK: <div class="math-block"> has no $$ delimiters '
                f'-- {_snippet(content)}'
            ))
        elif dd_count % 2 != 0:
            # Odd number of $$ means one is unclosed
            issues.append(Issue(
                PRIORITY, CHECK_ID, None, line,
                f'BROKEN_MATH_BLOCK: <div class="math-block"> has mismatched $$ '
                f'delimiters ({dd_count} found) -- {_snippet(content)}'
            ))

    return issues


def check_unclosed_delimiter(html):
    """Check 6: Mismatched $ delimiters within a line."""
    issues = []
    lines = html.split("\n")

    for i, line_text in enumerate(lines, 1):
        # Calculate absolute position of line start
        line_offset = sum(len(l) + 1 for l in lines[:i - 1])

        # Skip lines inside code blocks
        if _is_inside_code_block(html, line_offset):
            continue

        # Skip lines inside HTML tags that span the whole line (like <script>)
        stripped = line_text.strip()
        if stripped.startswith('<script') or stripped.startswith('</script'):
            continue

        # Remove $$ (display math) first, then count remaining $
        no_display = line_text.replace('$$', '')

        # Remove matched inline math $...$ pairs (non-greedy)
        no_matched = re.sub(r'\$[^$]+\$', '', no_display)

        # Remove currency $ (e.g., $12, $0.50, $ 300, $12K, $0.01/query)
        no_currency = re.sub(r'\$\s*[\d,]+(?:\.\d+)?(?:[KkMmBb])?(?:/[\w,]+)*', '', no_matched)
        # Also remove &#36; HTML entity for dollar sign
        no_currency = no_currency.replace('&#36;', '')
        # Remove $ inside code-like contexts (e.g., ${VARIABLE}, '$')
        no_currency = re.sub(r"\$\{[^}]*\}", '', no_currency)
        no_currency = re.sub(r"'\$'", '', no_currency)
        # Remove shell prompt $ (line starting with $ or at start of content)
        no_currency = re.sub(r'^\s*\$\s+', '', no_currency)
        # Remove $ in unit expressions like $/1M, ($)
        no_currency = re.sub(r'\$/', '', no_currency)
        no_currency = re.sub(r'\(\$\)', '', no_currency)
        # Remove lone $ surrounded by quotes (tokenizer output like ' $')
        no_currency = re.sub(r"'\s*\$\s*'", '', no_currency)
        # Remove $ inside <code> tags
        no_currency = re.sub(r'<code>[^<]*</code>', '', no_currency)
        # Remove escaped dollar in strings
        no_currency = re.sub(r"\\\$", '', no_currency)
        # Remove dollar-format patterns like $XX.XX, $X
        no_currency = re.sub(r'\$[A-Z]+(?:\.[A-Z]+)?', '', no_currency)

        dollar_count = no_currency.count('$')

        if dollar_count > 0 and dollar_count % 2 != 0:
            # Odd number of $ on this line
            # But only flag if the line is not continuing a multi-line context
            # Check if any $$ is open (which would mean we are inside display math)
            before = html[:line_offset]
            dd_before = before.count('$$')
            if dd_before % 2 == 1:
                # Inside a display math block, skip
                continue

            issues.append(Issue(
                PRIORITY, CHECK_ID, None, i,
                f'UNCLOSED_DELIMITER: odd number of $ delimiters ({dollar_count}) '
                f'on line -- {_snippet(line_text)}'
            ))

    return issues


# ---------------------------------------------------------------------------
# Framework interface
# ---------------------------------------------------------------------------

def run(filepath, html, context):
    """Run all math rendering checks on a single file.

    Returns a list of Issue namedtuples.
    """
    all_issues = []

    for check_fn in (
        check_prose_in_math_block,
        check_bare_math_span,
        check_html_entity_in_math,
        check_orphaned_math,
        check_broken_math_block,
        check_unclosed_delimiter,
    ):
        for issue in check_fn(html):
            # Replace None filepath with actual filepath
            all_issues.append(Issue(
                issue.priority, issue.check_id, filepath,
                issue.line, issue.message
            ))

    return all_issues


# ---------------------------------------------------------------------------
# Standalone mode
# ---------------------------------------------------------------------------

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    json_mode = "--json" in sys.argv

    # Collect target files
    target_files = []
    for f in root.rglob("*.html"):
        if any(skip in f.parts for skip in ("_archive", "node_modules", "vendor",
                                             ".git", "__pycache__", "deprecated",
                                             "templates")):
            continue
        target_files.append(f)

    all_results = {}
    total_issues = 0
    by_type = {}

    context = {"book_root": root}

    for filepath in sorted(target_files):
        try:
            html = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        issues = run(filepath, html, context)
        if issues:
            relpath = str(filepath.relative_to(root))
            file_issues = []
            for issue in issues:
                itype = issue.message.split(":")[0]
                by_type[itype] = by_type.get(itype, 0) + 1
                total_issues += 1
                file_issues.append({
                    "type": itype,
                    "priority": issue.priority,
                    "line": issue.line,
                    "message": issue.message,
                })
            all_results[relpath] = file_issues

    # Print summary
    print(f"=== Math Rendering Audit ({CHECK_ID}) ===")
    print(f"Files scanned: {len(target_files)}")
    print(f"Files with issues: {len(all_results)}")
    print(f"Total issues: {total_issues}")
    print()
    if by_type:
        print("Issues by type:")
        for itype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {itype}: {count}")
        print()

    for relpath, file_issues in sorted(all_results.items()):
        for issue in file_issues:
            print(f"[{issue['priority']}] {issue['type']} | {relpath}:{issue['line']} | {issue['message']}")

    if json_mode:
        print("\n--- JSON ---")
        print(json.dumps(all_results, indent=2))

    return total_issues


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)

"""
Fix math-prose mixing in $$...$$ display blocks.

Scans all HTML files for $$...$$ blocks that contain \\textbf{Title}
followed by prose text. Converts each block so that:
  - Titles become <p><strong>Title</strong></p> in HTML
  - Prose descriptions become HTML paragraphs
  - Only actual math formulas remain inside $$...$$ blocks

Conservative: blocks that cannot be confidently parsed are logged
for manual review rather than modified.
"""

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOG_MANUAL = []


# ---------------------------------------------------------------------------
# Brace-aware parsing
# ---------------------------------------------------------------------------

def find_matching_brace(s, start):
    """
    Given a string and the index of an opening '{', find the matching '}'.
    Returns the index of the closing brace, or -1 if not found.
    """
    depth = 0
    for i in range(start, len(s)):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_textbf(s, pos):
    """
    At position pos in string s, we expect '\\textbf{'.
    Extract the full content including nested braces.
    Returns (content, end_pos) where end_pos is after the closing '}'.
    """
    prefix = "\\textbf{"
    if not s[pos:].startswith(prefix):
        return None, pos
    brace_start = pos + len(prefix) - 1  # index of the '{'
    brace_end = find_matching_brace(s, brace_start)
    if brace_end == -1:
        return None, pos
    content = s[brace_start + 1:brace_end]
    return content, brace_end + 1


# ---------------------------------------------------------------------------
# Math operators for classification
# ---------------------------------------------------------------------------

MATH_OPS = [
    "\\cdot", "\\sum", "\\Sigma", "\\frac", "\\exp", "\\log",
    "\\sigma", "\\pi", "\\beta", "\\alpha", "\\lambda", "\\gamma",
    "\\tau", "\\epsilon", "\\eta", "\\Omega", "\\operatorname",
    "\\sqrt", "\\cos", "\\sin", "\\min", "\\max", "\\lceil",
    "\\rceil", "\\odot", "\\rightarrow", "_{", "^{", "\\times",
    "\\leq", "\\geq", "\\in",
]


def count_math_ops(s):
    return sum(1 for op in MATH_OPS if op in s)


def count_english_words(s):
    """Count English words (3+ alpha chars) outside LaTeX commands."""
    t = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", s)
    t = re.sub(r"\\[a-zA-Z]+", " ", t)
    t = re.sub(r"&[A-Za-z#0-9x]+;", " ", t)
    t = re.sub(r"[_^{}()|/\[\].,;:=+*<>\\0-9\-]", " ", t)
    words = [w for w in t.split() if len(w) >= 3 and w.isalpha()]
    return len(words)


def has_equation(s):
    """Check if string contains an equation pattern."""
    return bool(re.search(r"[A-Za-z_}\)]\s*=\s*[A-Za-z_\\{(0-9\-]", s))


def is_formula_line(line):
    """Determine if a line is a math formula vs prose."""
    s = line.strip()
    if not s:
        return False

    # Bullet lines with formulas
    if s.startswith("&bull;") or s.startswith("\\bullet"):
        if "=" in s or "\\times" in s or "\\cdot" in s:
            return True
        return False

    # Sub-titles are not formulas
    if s.startswith("\\textbf{"):
        return False

    # Lines beginning with \text{where/and/for/if/or} are typically
    # "where-clauses" that explain variables; classify by checking
    # whether the rest is dense math or mostly English
    if re.match(r"^\\text\{(?:where|and)\}", s):
        # If the rest of the line after the \text{} has many English words
        # relative to math ops, classify as prose
        rest = re.sub(r"^\\text\{[^}]*\}\s*", "", s)
        ew = count_english_words(rest)
        mo = count_math_ops(rest)
        if ew >= 5 and mo <= 2:
            return False
        # Otherwise keep as math (it has inline formulas)
        if mo >= 2:
            return True
        return False

    math_ops = count_math_ops(s)
    eng_words = count_english_words(s)
    eq = has_equation(s)

    # Strong formula
    if eq and math_ops >= 2:
        return True

    # Lines starting with L_{...}, D_{...} etc with equation
    if re.match(r"^[A-Z]_\{", s) and (eq or math_ops >= 1):
        return True

    # Simple assignment: y = ..., W' = ...
    if re.match(r"^[a-zA-Z]['\s]*(?:_\{[^}]*\})?\s*=", s):
        return True

    # Known formula names
    first_word = s.split()[0].rstrip("=:({") if s.split() else ""
    known_names = {
        "BLEU", "BM25", "RRF", "SLERP", "ROUGE", "PSI", "CLIP",
        "Faithfulness", "Relevancy", "ContextPrecision", "ContextRecall",
        "TopK", "score", "consistency", "agree", "recency", "relevance",
        "importance",
    }
    if first_word in known_names and (eq or math_ops >= 1):
        return True

    # Function-like: x'(t) = ..., g(x) = ...
    if re.match(r"^[a-z]['\s]*(?:\(|_\{)", s) and eq:
        return True

    # High math density
    if math_ops >= 3 and eng_words <= 3:
        return True
    if eq and eng_words <= 2:
        return True

    # Many English words = prose
    if eng_words >= 4:
        return False

    if math_ops >= 2:
        return True
    if eq and math_ops >= 1:
        return True
    if eng_words >= 2:
        return False
    if math_ops >= 1:
        return True

    return False


# ---------------------------------------------------------------------------
# Prose lines that look like formulas but are really descriptive
# (e.g. "Full fine-tuning parameters per weight matrix: d \times k")
# These contain a colon followed by a simple expression, not a real formula.
# ---------------------------------------------------------------------------

def is_labeled_value_line(line):
    """
    Lines like 'PQ storage per vector: m bytes' or
    'Full fine-tuning parameters per weight matrix: d \\times k'
    These are labeled values, best rendered as prose with inline math.
    """
    s = line.strip()
    if ":" in s:
        before_colon = s.split(":")[0]
        ew = count_english_words(before_colon)
        if ew >= 3:
            return True
    return False


# ---------------------------------------------------------------------------
# Prose cleaning
# ---------------------------------------------------------------------------

def clean_prose(text):
    """Convert LaTeX text to readable HTML prose."""
    t = text
    # \text{word} -> word
    t = re.sub(r"\\text\{([^}]*)\}", lambda m: m.group(1), t)
    # \textbf{word} -> <strong>word</strong>
    t = re.sub(r"\\textbf\{([^}]*)\}", lambda m: "<strong>" + m.group(1) + "</strong>", t)
    # \operatorname{X} -> X
    t = re.sub(r"\\operatorname\{([^}]*)\}", lambda m: m.group(1), t)

    # HTML entities
    replacements = {
        "&Ropf;": "\u211D",
        "&Lscr;": "\u2112",
        "&bull;": "\u2022",
    }
    for old, new in replacements.items():
        t = t.replace(old, new)

    # Combining accent characters
    t = t.replace("&#x0302;", "\u0302")
    t = t.replace("&#x0304;", "\u0304")

    # LaTeX sub/superscripts
    t = re.sub(r"_\{([^}]*)\}", lambda m: "<sub>" + m.group(1) + "</sub>", t)
    t = re.sub(r"\^\{([^}]*)\}", lambda m: "<sup>" + m.group(1) + "</sup>", t)

    # Common LaTeX symbols
    sym_map = [
        ("\\in", "\u2208"), ("\\times", "\u00D7"), ("\\cdot", "\u00B7"),
        ("\\leq", "\u2264"), ("\\geq", "\u2265"),
        ("\\rightarrow", "\u2192"), ("\\leftarrow", "\u2190"),
        ("\\pi", "\u03C0"), ("\\beta", "\u03B2"), ("\\alpha", "\u03B1"),
        ("\\lambda", "\u03BB"), ("\\gamma", "\u03B3"), ("\\tau", "\u03C4"),
        ("\\sigma", "\u03C3"), ("\\epsilon", "\u03B5"), ("\\eta", "\u03B7"),
        ("\\Delta", "\u0394"), ("\\Omega", "\u03A9"),
    ]
    for old, new in sym_map:
        t = t.replace(old, new)

    t = t.replace("\\;", " ")
    t = t.replace("\\,", " ")
    t = t.replace("\\\\", "")
    # Remove leftover backslashes (but not in HTML)
    t = re.sub(r"\\(?![<>])", "", t)
    t = re.sub(r"  +", " ", t)
    return t.strip()


def clean_math(text):
    """Clean up a math formula for proper KaTeX rendering."""
    t = text
    t = t.replace("&Ropf;", "\\mathbb{R}")
    t = t.replace("&Lscr;", "\\mathscr{L}")

    # Combining accent chars
    def hat_repl(m):
        return "\\hat{" + m.group(1) + "}"
    t = re.sub(r"(\w)&#x0302;", hat_repl, t)
    t = t.replace("&#x0302;", "\\hat{}")

    def bar_repl(m):
        return "\\bar{" + m.group(1) + "}"
    t = re.sub(r"(\w)&#x0304;", bar_repl, t)
    t = t.replace("&#x0304;", "\\bar{}")

    t = t.replace("&bull;", "\\bullet")

    # Fix \text{word} spacing for small connector words in math
    for word in ["and", "for", "if", "where", "or"]:
        t = t.replace("\\text{" + word + "}", "\\text{ " + word + " }")

    lines = t.split("\n")
    lines = [l.strip() for l in lines]
    t = "\n".join(lines)
    return t.strip()


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

def split_on_line_breaks(content):
    """
    Split block content on LaTeX line breaks.
    \\ \\ = paragraph break (double), \\ = line break (single).
    Returns list of (text, is_para_break) where is_para_break indicates
    a paragraph break preceded the text.
    """
    # Normalize: \\ \\ (with whitespace variations) -> PARA marker
    # Then remaining \\ -> LINE marker
    c = content

    # Double breaks: \\ followed by whitespace and another \\
    c = re.sub(r"\\\\\s*\\\\", "<<PARA>>", c)

    # Single breaks: remaining \\
    # Be careful not to match \\\\ inside LaTeX commands like \\hat
    # The pattern is: backslash-backslash at line end or before whitespace
    c = re.sub(r"\\\\(?=\s|$)", "<<LINE>>", c)

    # Split on PARA markers first
    para_parts = c.split("<<PARA>>")

    lines = []
    for i, part in enumerate(para_parts):
        sub_lines = part.split("<<LINE>>")
        for j, sl in enumerate(sub_lines):
            sl = sl.strip()
            if sl:
                is_para = (i > 0 and j == 0)
                lines.append((sl, is_para))

    return lines


def parse_block(inner):
    """
    Parse $$...$$ inner content into (type, content) segments.
    Types: 'title', 'prose', 'math'.
    """
    content = inner.strip()
    raw_lines = split_on_line_breaks(content)

    segments = []

    for line_text, _is_para in raw_lines:
        lt = line_text.strip()
        if not lt:
            continue

        # Check for title: \textbf{...} at start
        if lt.startswith("\\textbf{"):
            title_content, end_pos = extract_textbf(lt, 0)
            if title_content is not None:
                # Clean \text{} inside title
                tc = re.sub(r"\\text\{([^}]*)\}", lambda m: m.group(1), title_content)
                segments.append(("title", tc))

                # Handle remainder after the title
                remainder = lt[end_pos:].strip()
                # Strip leading period or colon
                if remainder and remainder[0] in ".:":
                    remainder = remainder[1:].strip()

                if remainder:
                    # The remainder might mix prose + formula, e.g.:
                    # "Given a query q \text{and} a candidate memory m, the score combines..."
                    # Classify as prose or math
                    if is_labeled_value_line(remainder):
                        segments.append(("prose", remainder))
                    elif is_formula_line(remainder):
                        segments.append(("math", remainder))
                    else:
                        segments.append(("prose", remainder))
                continue

        # Labeled value lines (e.g., "PQ storage per vector: m bytes")
        if is_labeled_value_line(lt) and not is_formula_line(lt):
            segments.append(("prose", lt))
            continue

        # Classify as formula or prose
        if is_formula_line(lt):
            segments.append(("math", lt))
        else:
            segments.append(("prose", lt))

    return segments


def render_segments(segments):
    """Convert segments to HTML with separate $$ blocks for math."""
    parts = []
    math_buf = []

    def flush_math():
        if not math_buf:
            return
        combined = " \\\\\n".join(math_buf)
        combined = clean_math(combined)
        parts.append("\n$$" + combined + "$$\n")
        math_buf.clear()

    for stype, content in segments:
        if stype == "title":
            flush_math()
            tc = content.strip().rstrip(".").rstrip(":").strip()
            parts.append("\n<p><strong>" + tc + ".</strong></p>\n")

        elif stype == "prose":
            flush_math()
            html = clean_prose(content)
            if html:
                parts.append("\n<p>" + html + "</p>\n")

        elif stype == "math":
            math_buf.append(content)

    flush_math()

    result = "".join(parts)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_block(match, filepath):
    """Process a single $$...$$ match."""
    full = match.group(0)
    inner = match.group(1)

    if "\\textbf{" not in inner:
        return full
    if len(inner.strip()) < 30:
        return full

    try:
        segments = parse_block(inner)
        has_title = any(s[0] == "title" for s in segments)
        if not has_title:
            LOG_MANUAL.append((str(filepath), "No title found", inner[:80]))
            return full
        return render_segments(segments)
    except Exception as exc:
        LOG_MANUAL.append((str(filepath), "Error: " + str(exc), inner[:80]))
        return full


def process_file(filepath):
    """Process one HTML file. Return (modified, block_count)."""
    text = Path(filepath).read_text(encoding="utf-8")
    original = text

    pat = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
    count = [0]

    def repl(m):
        result = process_block(m, filepath)
        if result != m.group(0):
            count[0] += 1
        return result

    text = pat.sub(repl, text)

    if text != original:
        Path(filepath).write_text(text, encoding="utf-8")
        return True, count[0]
    return False, 0


def find_html_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in ("node_modules", ".git", "__pycache__", "vendor")
        ]
        for fn in filenames:
            if fn.endswith(".html"):
                yield Path(dirpath) / fn


def main():
    total_files = 0
    modified_files = 0
    total_blocks = 0

    print("Scanning HTML files under " + str(ROOT) + " ...")
    print()

    for fp in sorted(find_html_files(ROOT)):
        rel = fp.relative_to(ROOT)
        if str(rel).startswith("scripts"):
            continue

        mod, cnt = process_file(fp)
        total_files += 1
        if mod:
            modified_files += 1
            total_blocks += cnt
            print("  FIXED  " + str(rel) + "  (" + str(cnt) + " block(s))")

    print()
    print("Scanned " + str(total_files) + " files.")
    print("Modified " + str(modified_files) + " files (" + str(total_blocks) + " blocks fixed).")

    if LOG_MANUAL:
        print()
        print("MANUAL REVIEW needed (" + str(len(LOG_MANUAL)) + " blocks):")
        for fpath, reason, snippet in LOG_MANUAL:
            print("  File: " + fpath)
            print("  Reason: " + reason)
            print("  Snippet: " + snippet + "...")
            print()


if __name__ == "__main__":
    main()

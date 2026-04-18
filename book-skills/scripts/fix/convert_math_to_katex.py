"""
Convert HTML entity math to KaTeX LaTeX syntax.

Phase 1: Add KaTeX <link>/<script> tags to all HTML files.
Phase 2: Convert <div class="math-block"> content to $$...$$ LaTeX.
Phase 3: Convert <span class="math"> content to $...$ LaTeX.
Phase 4: Normalize inline-styled math paragraphs to math-block divs.
"""

import re
from pathlib import Path
from collections import defaultdict

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles", "agents", "_lab_fragments", "vendor"}

# HTML entity to LaTeX mapping
ENTITY_MAP = {
    # Greek lowercase
    "&alpha;": r"\alpha", "&beta;": r"\beta", "&gamma;": r"\gamma",
    "&delta;": r"\delta", "&epsilon;": r"\epsilon", "&zeta;": r"\zeta",
    "&eta;": r"\eta", "&theta;": r"\theta", "&iota;": r"\iota",
    "&kappa;": r"\kappa", "&lambda;": r"\lambda", "&mu;": r"\mu",
    "&nu;": r"\nu", "&xi;": r"\xi", "&pi;": r"\pi",
    "&rho;": r"\rho", "&sigma;": r"\sigma", "&tau;": r"\tau",
    "&phi;": r"\phi", "&chi;": r"\chi", "&psi;": r"\psi", "&omega;": r"\omega",
    # Greek uppercase
    "&Alpha;": r"A", "&Beta;": r"B", "&Gamma;": r"\Gamma",
    "&Delta;": r"\Delta", "&Theta;": r"\Theta", "&Lambda;": r"\Lambda",
    "&Sigma;": r"\Sigma", "&Phi;": r"\Phi", "&Psi;": r"\Psi", "&Omega;": r"\Omega",
    "&Pi;": r"\Pi",
    # Unicode Greek (literal characters)
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "λ": r"\lambda", "μ": r"\mu", "σ": r"\sigma", "τ": r"\tau",
    "φ": r"\phi", "π": r"\pi", "ω": r"\omega",
    "Σ": r"\Sigma", "Π": r"\Pi", "Δ": r"\Delta", "Ω": r"\Omega",
    # Operators
    "&times;": r"\times", "&middot;": r"\cdot", "&divide;": r"\div",
    "&plusmn;": r"\pm", "&minus;": r"-",
    "&sum;": r"\sum", "&prod;": r"\prod", "&int;": r"\int",
    "&nabla;": r"\nabla", "&part;": r"\partial",
    "&radic;": r"\sqrt", "&infin;": r"\infty",
    "&odot;": r"\odot", "&oplus;": r"\oplus", "&otimes;": r"\otimes",
    # Relations
    "&le;": r"\leq", "&ge;": r"\geq", "&ne;": r"\neq",
    "&asymp;": r"\approx", "&approx;": r"\approx",
    "&equiv;": r"\equiv", "&prop;": r"\propto",
    "&isin;": r"\in", "&notin;": r"\notin", "&sub;": r"\subset",
    # Arrows
    "&rarr;": r"\rightarrow", "&larr;": r"\leftarrow",
    "&harr;": r"\leftrightarrow", "&rArr;": r"\Rightarrow",
    "→": r"\rightarrow", "←": r"\leftarrow",
    # Other
    "&forall;": r"\forall", "&exist;": r"\exists",
    "&empty;": r"\emptyset", "&perp;": r"\perp",
    "&#770;": r"\hat", "&#x302;": r"\hat",  # combining circumflex
    "&hellip;": r"\ldots", "…": r"\ldots",
    "∇": r"\nabla", "∂": r"\partial", "∞": r"\infty",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset",
    "×": r"\times", "·": r"\cdot", "÷": r"\div", "±": r"\pm",
    "&cap;": r"\cap", "&cup;": r"\cup",
    # Special
    "&amp;": r"\&",
}

def html_to_latex(html_content):
    """Convert HTML math content to LaTeX string."""
    text = html_content.strip()

    # Remove <br> tags (multi-line formulas use \\ in LaTeX)
    text = re.sub(r'<br\s*/?\s*>', r' \\\\ ', text)

    # Convert <sub>...</sub> to _{...}
    text = re.sub(r'<sub>(.*?)</sub>', r'_{\1}', text, flags=re.DOTALL)

    # Convert <sup>...</sup> to ^{...}
    text = re.sub(r'<sup>(.*?)</sup>', r'^{\1}', text, flags=re.DOTALL)

    # Convert <em>...</em> and <i>...</i> to \text{...} or just keep as-is
    text = re.sub(r'<em>(.*?)</em>', r'\1', text)
    text = re.sub(r'<i>(.*?)</i>', r'\1', text)

    # Convert <strong>...</strong> and <b>...</b>
    text = re.sub(r'<strong>(.*?)</strong>', r'\\textbf{\1}', text)
    text = re.sub(r'<b>(.*?)</b>', r'\\textbf{\1}', text)

    # Remove any remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Apply entity map
    for entity, latex in ENTITY_MAP.items():
        text = text.replace(entity, f" {latex} " if len(latex) > 1 and latex.startswith("\\") else latex)

    # Fix hat notation: X\hat -> \hat{X}
    text = re.sub(r'(\w) \\hat ', r'\\hat{\1} ', text)
    text = re.sub(r'(\w)\\hat', r'\\hat{\1}', text)

    # Fix sqrt: \sqrt X -> \sqrt{X} (only if not already braced)
    text = re.sub(r'\\sqrt\s+([A-Za-z])', r'\\sqrt{\1}', text)

    # Convert common text words to \text{} in math context
    for word in ['softmax', 'sigmoid', 'log', 'exp', 'max', 'min', 'argmax', 'argmin',
                 'tanh', 'relu', 'gelu', 'dim', 'diag', 'trace', 'det',
                 'Attention', 'LayerNorm', 'RMSNorm', 'FFN', 'MultiHead',
                 'round', 'clamp', 'clip', 'sign', 'abs',
                 'where', 'if', 'otherwise', 'for', 'and', 'or',
                 'DPO', 'PPO', 'KL', 'BCE', 'MSE', 'SFT', 'RLHF']:
        # Only wrap if it appears as a standalone word in math context
        text = re.sub(r'\b' + word + r'\b(?![_{^])', r'\\text{' + word + '}', text)

    # Fix common LaTeX issues
    # Double backslashes from conversion
    text = re.sub(r'\\\\text', r'\\text', text)
    # Remove excess spaces
    text = re.sub(r'  +', ' ', text)
    text = text.strip()

    return text

def find_html_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        files.append(f)
    return sorted(files)

def get_katex_depth(filepath):
    """Calculate relative path depth to vendor/katex from this file."""
    rel = filepath.relative_to(BASE)
    depth = len(rel.parts) - 1  # subtract filename
    return "../" * depth

def add_katex_tags(filepath):
    """Add KaTeX CSS/JS tags to <head> if not already present."""
    text = filepath.read_text(encoding="utf-8")
    if "katex" in text.lower():
        return False  # Already has KaTeX

    depth = get_katex_depth(filepath)

    katex_tags = f"""    <link rel="stylesheet" href="{depth}vendor/katex/katex.min.css">
    <script defer src="{depth}vendor/katex/katex.min.js"></script>
    <script defer src="{depth}vendor/katex/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {{
            delimiters: [
                {{left: '$$', right: '$$', display: true}},
                {{left: '$', right: '$', display: false}}
            ],
            throwOnError: false
        }});"></script>"""

    # Insert before </head>
    text = text.replace("</head>", katex_tags + "\n</head>")
    filepath.write_text(text, encoding="utf-8")
    return True

def convert_math_blocks(filepath):
    """Convert math-block divs and inline math spans to KaTeX LaTeX."""
    text = filepath.read_text(encoding="utf-8")
    orig = text
    block_count = 0
    inline_count = 0

    # Convert <div class="math-block">...</div> content to $$...$$
    def convert_block(m):
        nonlocal block_count
        full = m.group(0)
        inner = m.group(1)

        # Preserve math-block-label if present
        label_match = re.search(r'<div class="math-block-label">(.*?)</div>', inner)
        label_html = ""
        if label_match:
            label_html = label_match.group(0) + "\n    "
            inner = inner.replace(label_match.group(0), "")

        # Preserve math-where if present
        where_match = re.search(r'<(?:div|span) class="math-where">(.*?)</(?:div|span)>', inner, re.DOTALL)
        where_html = ""
        if where_match:
            where_html = "\n    " + where_match.group(0)
            inner = inner.replace(where_match.group(0), "")

        latex = html_to_latex(inner)
        if not latex:
            return full

        block_count += 1
        return f'<div class="math-block">\n    {label_html}$${latex}$$\n    {where_html}\n</div>'

    text = re.sub(
        r'<div class="math-block"[^>]*>(.*?)</div>',
        convert_block,
        text,
        flags=re.DOTALL
    )

    # Convert <span class="math">...</span> to $...$
    def convert_inline(m):
        nonlocal inline_count
        inner = m.group(1)
        latex = html_to_latex(inner)
        if not latex or len(latex) < 2:
            return m.group(0)  # Skip trivially short
        inline_count += 1
        return f'<span class="math">${latex}$</span>'

    text = re.sub(
        r'<span class="math">(.*?)</span>',
        convert_inline,
        text,
        flags=re.DOTALL
    )

    if text != orig:
        filepath.write_text(text, encoding="utf-8")

    return block_count, inline_count

def main():
    files = find_html_files()
    print(f"Processing {len(files)} HTML files for KaTeX integration...\n")

    # Phase 1: Add KaTeX tags
    print("Phase 1: Adding KaTeX tags to HTML files...")
    tags_added = 0
    for f in files:
        if add_katex_tags(f):
            tags_added += 1
    print(f"  Added KaTeX tags to {tags_added} files\n")

    # Phase 2+3: Convert math content
    print("Phase 2+3: Converting math to LaTeX...")
    total_blocks = 0
    total_inline = 0
    files_converted = 0

    for f in files:
        blocks, inlines = convert_math_blocks(f)
        if blocks or inlines:
            files_converted += 1
            total_blocks += blocks
            total_inline += inlines
            if blocks + inlines >= 3:
                print(f"  {f.relative_to(BASE)}: {blocks} blocks, {inlines} inline")

    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  KaTeX tags added to: {tags_added} files")
    print(f"  Math blocks converted: {total_blocks}")
    print(f"  Inline math converted: {total_inline}")
    print(f"  Files with conversions: {files_converted}")

if __name__ == "__main__":
    main()

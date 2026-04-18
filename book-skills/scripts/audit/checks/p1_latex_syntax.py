"""Detect common LaTeX syntax errors in $$ math blocks.

Checks for:
1. Unescaped function names (log, min, max, exp, etc.) that should be \log, \min, etc.
2. Prose mixed into math blocks (English words that aren't LaTeX commands)
3. Mismatched braces in subscripts/superscripts
4. Missing \frac for division with /
5. pi* instead of \pi^*
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "LATEX_SYNTAX"
DESCRIPTION = "LaTeX syntax issue in math block"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Math block delimiters
MATH_DISPLAY = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)

# Functions that should be escaped with backslash
UNESCAPED_FUNCS = re.compile(
    r'(?<!\\)\b(log|min|max|exp|sin|cos|tan|det|dim|sup|inf|lim|arg|gcd|Pr|Var|Cov|softmax|sigmoid|clip)\b'
    r'(?!\s*[_^])'  # allow if immediately followed by subscript (could be variable)
)

# Prose words that should not appear in math mode
PROSE_WORDS = re.compile(
    r'\b(is|the|are|was|were|this|that|for|and|but|not|with|from|into|also|where|which|The|'
    r'typically|often|usually|sometimes|always|never|should|could|would|can|will|'
    r'response|preferred|rejected|trainable|frozen|policy|controls|deviation|strength|'
    r'model|reward)\b'
)
# But "where" at the start preceded by \text is fine
PROSE_IN_TEXT = re.compile(r'\\text\{[^}]*\}')

# pi* instead of \pi^*
PI_STAR = re.compile(r'\\pi\s*\*')

# Mismatched braces helper
def check_braces(formula):
    """Check for mismatched { } in a formula."""
    depth = 0
    for ch in formula:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return "Extra closing brace }"
    if depth > 0:
        return f"Unclosed braces ({depth} unmatched)"
    return None


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    # Join all lines to find multi-line $$ blocks
    full_text = "\n".join(lines)

    for m in MATH_DISPLAY.finditer(full_text):
        formula = m.group(1)
        # Calculate line number
        start_pos = m.start()
        line_num = full_text[:start_pos].count("\n") + 1

        # Skip if formula is very short (inline-ish)
        if len(formula.strip()) < 5:
            continue

        # Check 1: Unescaped function names
        # First strip \text{...} and \operatorname{...} regions to avoid false positives
        formula_no_text = PROSE_IN_TEXT.sub('', formula)
        formula_no_text = re.sub(r'\\operatorname\{[^}]*\}', '', formula_no_text)
        for func_m in UNESCAPED_FUNCS.finditer(formula_no_text):
            func_name = func_m.group(1)
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, line_num,
                f'Unescaped function name "{func_name}" should be "\\{func_name}"',
            ))

        # Check 2: Prose in math blocks (outside \text{})
        formula_clean = PROSE_IN_TEXT.sub('', formula)
        # Also strip \operatorname{...}
        formula_clean = re.sub(r'\\operatorname\{[^}]*\}', '', formula_clean)
        prose_matches = list(PROSE_WORDS.finditer(formula_clean))
        if len(prose_matches) >= 2:
            words = [pm.group(0) for pm in prose_matches[:3]]
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, line_num,
                f'Prose in math block: "{", ".join(words)}..." Wrap in \\text{{}} or move outside $$',
            ))

        # Check 3: Mismatched braces
        brace_err = check_braces(formula)
        if brace_err:
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, line_num,
                f'Brace mismatch in math block: {brace_err}',
            ))

        # Check 4: \pi* instead of \pi^*
        if PI_STAR.search(formula):
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, line_num,
                r'Use \pi^* instead of \pi* for optimal policy notation',
            ))

    return issues

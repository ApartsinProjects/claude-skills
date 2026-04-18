"""Detect code blocks that encode decision trees, lookup tables, or classification
logic that would be better represented as an HTML table.

Heuristics (any TWO of these in a single code block triggers the check):
  1. Enum class with 3+ string members
  2. Dict literal with 3+ keys mapping to lists of strings
  3. @dataclass with all-str fields and no computation
  4. if/elif chain with 3+ branches returning enum/string values
  5. Block is in a non-engineering chapter (safety, strategy, frontiers, ethics)
"""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "DECORATIVE_CODE"
DESCRIPTION = "Code block encodes a decision tree or lookup table better suited to an HTML table"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Chapters where code should teach engineering, not encode taxonomies
NON_ENGINEERING_DIRS = [
    "module-32-",  # safety, ethics, regulation
    "module-33-",  # strategy
    "module-34-",  # emerging architectures (prose-heavy)
    "module-35-",  # AI and society
]

CODE_BLOCK_RE = re.compile(r'<pre><code[^>]*class="language-python"[^>]*>(.*?)</code></pre>', re.DOTALL)
ENUM_RE = re.compile(r'class\s+\w+\(Enum\)')
DICT_LITERAL_RE = re.compile(r'\w+\s*=\s*\{[^}]*"[^"]+"\s*:\s*\[')
DATACLASS_RE = re.compile(r'@dataclass')
STR_FIELDS_RE = re.compile(r':\s*str\b')
IF_RETURN_CHAIN_RE = re.compile(r'(if |elif )')
RETURN_STRING_RE = re.compile(r'return\s+(RiskTier\.\w+|["\'])')


def _count_signals(code):
    """Count how many decorative-code signals are present."""
    signals = 0

    if ENUM_RE.search(code):
        # Check for 3+ members
        members = re.findall(r'\w+\s*=\s*"[^"]+"', code)
        if len(members) >= 3:
            signals += 1

    if DICT_LITERAL_RE.search(code):
        # Check for 3+ keys
        dict_keys = re.findall(r'"[^"]+"\s*:\s*\[', code)
        if len(dict_keys) >= 3:
            signals += 1

    if DATACLASS_RE.search(code):
        str_fields = STR_FIELDS_RE.findall(code)
        non_str_fields = re.findall(r':\s*(bool|int|float|list|dict|Optional)\b', code)
        # Only flag if mostly string fields (data-only lookup class)
        if len(str_fields) >= 3 and len(non_str_fields) == 0:
            signals += 1

    if_count = len(IF_RETURN_CHAIN_RE.findall(code))
    return_count = len(RETURN_STRING_RE.findall(code))
    if if_count >= 3 and return_count >= 3:
        signals += 1

    return signals


def run(filepath, html, context):
    issues = []

    # Only flag in non-engineering chapters (broadest signal)
    is_non_eng = any(d in str(filepath).replace("\\", "/") for d in NON_ENGINEERING_DIRS)

    for m in CODE_BLOCK_RE.finditer(html):
        code = m.group(1)
        line_num = html[:m.start()].count("\n") + 1
        code_lines = code.count("\n") + 1

        # Skip short code blocks (< 15 lines are probably fine)
        if code_lines < 15:
            continue

        signals = _count_signals(code)

        # Require 4+ signals in all chapters (thresholds of 2-3 produced
        # false positives on legitimate teaching code that uses
        # Enum + dataclass + dict patterns for demonstration)
        threshold = 4

        if signals >= threshold:
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, line_num,
                f"Code block ({code_lines} lines, {signals} decorative signals) "
                f"appears to encode a lookup/decision table. Consider replacing with an HTML table."
            ))

    return issues

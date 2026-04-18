"""Fix unescaped LaTeX function names in $$ math blocks.

Replaces bare log, exp, sin, cos, min, max, etc. with \log, \exp, etc.
Special case: softmax -> \operatorname{softmax} (not a standard LaTeX command).
"""
import re
from pathlib import Path

MATH_BLOCK = re.compile(r'(\$\$)(.*?)(\$\$)', re.DOTALL)

# Standard LaTeX math operators
STANDARD_FUNCS = ['log', 'exp', 'sin', 'cos', 'tan', 'min', 'max', 'det', 'dim',
                  'sup', 'inf', 'lim', 'arg', 'gcd', 'Pr']

# Custom operators that need \operatorname{}
CUSTOM_FUNCS = ['softmax', 'sigmoid', 'clip']

def fix_formula(formula):
    """Fix unescaped function names in a LaTeX formula."""
    changed = False

    for func in STANDARD_FUNCS:
        pattern = re.compile(r'(?<!\\)\b' + func + r'\b')
        if pattern.search(formula):
            formula = pattern.sub('\\\\' + func, formula)
            changed = True

    for func in CUSTOM_FUNCS:
        pattern = re.compile(r'(?<!\\operatorname\{)(?<!\\)\b' + func + r'\b')
        if pattern.search(formula):
            formula = pattern.sub(r'\\operatorname{' + func + '}', formula)
            changed = True

    return formula, changed


files_fixed = 0
total_fixes = 0

for f in Path(".").rglob("*.html"):
    if any(skip in str(f) for skip in ["vendor", ".git", "node_modules", "deprecated"]):
        continue

    text = f.read_text(encoding="utf-8")
    if '$$' not in text:
        continue

    fix_count = [0]

    def replacer(m, counter=fix_count):
        prefix = m.group(1)
        formula = m.group(2)
        suffix = m.group(3)
        fixed, changed = fix_formula(formula)
        if changed:
            counter[0] += 1
        return prefix + fixed + suffix

    new_text = MATH_BLOCK.sub(replacer, text)

    if fix_count[0] > 0:
        f.write_text(new_text, encoding="utf-8")
        files_fixed += 1
        total_fixes += fix_count[0]

print(f"Fixed LaTeX function names in {total_fixes} math blocks across {files_fixed} files")

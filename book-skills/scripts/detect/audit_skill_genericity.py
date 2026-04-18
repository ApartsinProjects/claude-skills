"""
Audit all book-writers (textbook-chapter) agent skill files for
book-specific or subject-specific references that should be generalized.

Reports: file, line number, matched text, and the pattern that triggered it.
"""

import re
from pathlib import Path

SKILL_DIR = Path(r"C:\Users\apart\.claude\skills\textbook-chapter")

# Patterns that indicate book-specific references (case-insensitive)
BOOK_SPECIFIC_PATTERNS = [
    # Direct book title references
    (r"Building Conversational AI", "Book title reference"),
    (r"Conversational AI with LLMs", "Book title reference"),
    (r"LLMs and Agents", "Book title reference (may be generic, review)"),

    # Specific chapter/part structure
    (r"36[- ]chapter", "Hardcoded chapter count"),
    (r"10[- ]part", "Hardcoded part count"),
    (r"Part\s+(?:VI|VII|VIII|IX|X|I{1,3}V?)\b", "Hardcoded Part numeral"),
    (r"Chapter\s+\d{1,2}(?:\b|:)", "Hardcoded chapter number reference"),
    (r"Module\s+\d{1,2}", "Hardcoded module number"),
    (r"Section\s+\d+\.\d+", "Hardcoded section number"),

    # Specific topic references that make skills non-generic
    (r"transformer", "Subject-specific (transformer)"),
    (r"attention mechanism", "Subject-specific (attention)"),
    (r"GPT|BERT|LLaMA|Claude|Gemini", "Subject-specific model name"),
    (r"prompt engineering", "Subject-specific topic"),
    (r"fine[- ]?tun", "Subject-specific topic"),
    (r"RAG|retrieval.augmented", "Subject-specific topic"),
    (r"embeddings?\b", "Subject-specific topic"),
    (r"tokeniz", "Subject-specific topic"),

    # Specific persona names (from Wisdom Council, not production agents)
    (r"Tensor\b|Lexica\b|Token\b|Sage\b", "Wisdom Council persona name"),

    # Specific file paths
    (r"part-\d+-", "Hardcoded part directory path"),
    (r"module-\d{2}-", "Hardcoded module directory path"),

    # Edition references
    (r"Fifth Edition", "Edition-specific reference"),
    (r"2026\b", "Year-specific reference"),
]

# Patterns to EXCLUDE (these are generic/acceptable)
EXCLUDE_PATTERNS = [
    r"^\s*#",           # Markdown headings (context, not references)
    r"^\s*\|",          # Table rows
    r"^\s*```",         # Code blocks
    r"BOOK_CONFIG\.md", # Intentional reference to config
    r"example",         # Example text
    r"e\.g\.",          # Example markers
    r"for instance",    # Example markers
]

def audit_file(fpath: Path) -> list:
    findings = []
    try:
        lines = fpath.read_text(encoding="utf-8").splitlines()
    except Exception:
        return findings

    for i, line in enumerate(lines, 1):
        # Skip excluded patterns
        skip = False
        for exc in EXCLUDE_PATTERNS:
            if re.search(exc, line, re.IGNORECASE):
                skip = True
                break

        for pattern, category in BOOK_SPECIFIC_PATTERNS:
            matches = list(re.finditer(pattern, line, re.IGNORECASE))
            for m in matches:
                findings.append({
                    "file": fpath.name,
                    "line": i,
                    "category": category,
                    "match": m.group(),
                    "context": line.strip()[:120],
                    "excluded": skip,
                })
    return findings

def main():
    all_findings = []

    # Audit SKILL.md
    skill_md = SKILL_DIR / "SKILL.md"
    if skill_md.exists():
        all_findings.extend(audit_file(skill_md))

    # Audit all agent files
    agents_dir = SKILL_DIR / "agents"
    if agents_dir.exists():
        for f in sorted(agents_dir.glob("*.md")):
            all_findings.extend(audit_file(f))

    # Audit templates
    templates_dir = SKILL_DIR / "templates"
    if templates_dir.exists():
        for f in sorted(templates_dir.glob("*.md")):
            all_findings.extend(audit_file(f))

    # Report
    actionable = [f for f in all_findings if not f["excluded"]]
    excluded = [f for f in all_findings if f["excluded"]]

    print(f"Total findings: {len(all_findings)} ({len(actionable)} actionable, {len(excluded)} in excluded context)")
    print()

    # Group by category
    by_cat = {}
    for f in actionable:
        by_cat.setdefault(f["category"], []).append(f)

    for cat in sorted(by_cat.keys()):
        items = by_cat[cat]
        print(f"\n{'='*60}")
        print(f"  {cat} ({len(items)} occurrences)")
        print(f"{'='*60}")
        for item in items[:10]:  # Show first 10 per category
            print(f"  {item['file']}:{item['line']} - \"{item['match']}\"")
            print(f"    {item['context']}")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more")

if __name__ == "__main__":
    main()

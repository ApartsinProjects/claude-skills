"""
Comprehensive HTML conformance audit for the LLMCourse textbook.
Checks every section/chapter HTML file against the book's conventions.

Gradually upgradeable: add new checks by defining a function and adding
it to the CHECKS list. Each check returns a list of Issue namedtuples.

Usage:
    python audit_conformance.py                    # full audit
    python audit_conformance.py --part part-4      # audit one part
    python audit_conformance.py --file section-10.3.html  # audit one file
    python audit_conformance.py --check nav        # run only nav checks
    python audit_conformance.py --severity error   # only errors, skip warnings
"""

import re
import sys
import argparse
from pathlib import Path
from collections import namedtuple, defaultdict
from typing import List

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts",
                "templates", "styles", "vendor", "images", ".git",
                "part-6-agents-applications", "part-7-production-strategy"}

Issue = namedtuple("Issue", ["file", "line", "severity", "category", "message"])


# ============================================================
# UTILITY HELPERS
# ============================================================

def read_file(filepath):
    """Read file and return (text, lines) tuple."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        lines = text.split("\n")
        return text, lines
    except Exception as e:
        return None, None


def find_line(lines, pattern, start=0):
    """Find first line matching pattern (string or regex)."""
    for i, line in enumerate(lines):
        if i < start:
            continue
        if isinstance(pattern, str):
            if pattern in line:
                return i + 1  # 1-indexed
        else:
            if pattern.search(line):
                return i + 1
    return 0


def is_section_file(filepath):
    """Check if file is a chapter section (not index, not front-matter special)."""
    name = filepath.name
    return name.startswith("section-") and name.endswith(".html")


def is_chapter_index(filepath):
    """Check if file is a chapter/appendix index."""
    return (filepath.name == "index.html" and
            (filepath.parent.name.startswith("module-") or
             filepath.parent.name.startswith("appendix-")))


def get_chapter_num(filepath):
    """Extract chapter number from path, e.g., module-14 -> '14'."""
    parent = filepath.parent.name
    m = re.search(r"module-(\d+)", parent)
    if m:
        return m.group(1)
    m = re.search(r"appendix-(\w)", parent)
    if m:
        return m.group(1).upper()
    return None


# ============================================================
# CHECK: STRUCTURE
# ============================================================

def check_structure(filepath, text, lines) -> List[Issue]:
    """Check basic HTML structure: doctype, header, main, footer, nav."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if not text.strip().startswith("<!DOCTYPE html>"):
        issues.append(Issue(f, 1, "error", "structure", "Missing <!DOCTYPE html>"))

    if '<header class="chapter-header">' not in text:
        issues.append(Issue(f, 0, "error", "structure", "Missing <header class='chapter-header'>"))

    if "<main" not in text:
        issues.append(Issue(f, 0, "error", "structure", "Missing <main> element"))

    if "<footer>" not in text:
        issues.append(Issue(f, 0, "warning", "structure", "Missing <footer> element"))

    if 'class="chapter-nav"' not in text:
        issues.append(Issue(f, 0, "warning", "structure", "Missing <nav class='chapter-nav'>"))

    return issues


# ============================================================
# CHECK: HEADER
# ============================================================

def check_header(filepath, text, lines) -> List[Issue]:
    """Check header structure: book title link, toc link, part-label, chapter-label, h1."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if 'class="book-title-link"' not in text:
        issues.append(Issue(f, 0, "warning", "header", "Missing book-title-link in header nav"))

    if 'class="toc-link"' not in text:
        issues.append(Issue(f, 0, "warning", "header", "Missing toc-link in header nav"))

    if is_section_file(filepath) or is_chapter_index(filepath):
        if 'class="part-label"' not in text:
            issues.append(Issue(f, 0, "warning", "header", "Missing part-label div"))
        if 'class="chapter-label"' not in text and is_section_file(filepath):
            issues.append(Issue(f, 0, "warning", "header", "Missing chapter-label div"))

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL)
    if not h1_match:
        issues.append(Issue(f, 0, "error", "header", "Missing <h1> element"))

    return issues


# ============================================================
# CHECK: NAVIGATION
# ============================================================

def check_nav(filepath, text, lines) -> List[Issue]:
    """Check chapter-nav: no generic text, links present."""
    issues = []
    f = str(filepath.relative_to(BASE))

    nav_match = re.search(r'<nav\s+class="chapter-nav">(.*?)</nav>', text, re.DOTALL)
    if not nav_match:
        return issues

    nav = nav_match.group(1)
    ln = find_line(lines, 'class="chapter-nav"')

    # Check for generic link text
    generic_patterns = [
        "Next Chapter", "Previous Chapter", "Next Section", "Previous Section",
        "Next &rarr;", "&larr; Previous",
    ]
    for gp in generic_patterns:
        if gp in nav:
            issues.append(Issue(f, ln, "error", "nav",
                                f"Generic nav text found: '{gp}'. Use actual page title."))

    # Check for empty prev/next spans (okay for first/last page, warning otherwise)
    if '<span class="prev"></span>' in nav:
        issues.append(Issue(f, ln, "info", "nav", "Empty prev link (acceptable if first page)"))
    if '<span class="next"></span>' in nav:
        issues.append(Issue(f, ln, "info", "nav", "Empty next link (acceptable if last page)"))

    # Check up link exists
    if 'class="up"' not in nav:
        issues.append(Issue(f, ln, "warning", "nav", "Missing 'up' link in nav"))

    return issues


# ============================================================
# CHECK: FOOTER
# ============================================================

def check_footer(filepath, text, lines) -> List[Issue]:
    """Check footer format: title, copyright, last-updated."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if "<footer>" not in text:
        return issues

    footer_start = find_line(lines, "<footer>")

    if 'class="footer-title"' not in text:
        issues.append(Issue(f, footer_start, "warning", "footer", "Missing footer-title"))

    if "Alexander Apartsin" not in text or "Yehudit Aperstein" not in text:
        issues.append(Issue(f, footer_start, "warning", "footer", "Missing author names in copyright"))

    if 'class="footer-updated"' not in text:
        issues.append(Issue(f, footer_start, "warning", "footer", "Missing footer-updated with lastModified script"))

    if "document.lastModified" not in text:
        issues.append(Issue(f, footer_start, "warning", "footer", "Missing document.lastModified script in footer"))

    if 'toc.html' not in text:
        issues.append(Issue(f, footer_start, "warning", "footer", "Missing Contents link in footer"))

    return issues


# ============================================================
# CHECK: SECTION CONTENT ELEMENTS
# ============================================================

def check_section_content(filepath, text, lines) -> List[Issue]:
    """Check section-specific content: epigraph, prerequisites, big-picture, takeaways."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    # Epigraph
    if 'class="epigraph"' not in text:
        issues.append(Issue(f, 0, "warning", "content", "Missing epigraph blockquote"))

    # Prerequisites
    if 'class="prerequisites"' not in text:
        issues.append(Issue(f, 0, "warning", "content", "Missing prerequisites div"))

    # Big Picture callout
    if 'callout big-picture' not in text:
        issues.append(Issue(f, 0, "warning", "content", "Missing Big Picture callout"))

    # Key Takeaways
    if 'class="takeaways"' not in text and "Key Takeaways" not in text:
        issues.append(Issue(f, 0, "warning", "content", "Missing Key Takeaways section"))

    # What's Next
    if 'class="whats-next"' not in text and "What Comes Next" not in text and "What's Next" not in text:
        issues.append(Issue(f, 0, "info", "content", "Missing What's Next section"))

    return issues


# ============================================================
# CHECK: CALLOUT VALIDATION
# ============================================================

VALID_CALLOUT_TYPES = {
    "big-picture", "key-insight", "note", "warning", "tip",
    "fun-note", "practical-example", "research-frontier",
    "algorithm", "exercise",
}

def check_callouts(filepath, text, lines) -> List[Issue]:
    """Check callout markup: valid types, callout-title present."""
    issues = []
    f = str(filepath.relative_to(BASE))

    # Find all callout divs
    for m in re.finditer(r'class="callout\s+([^"]+)"', text):
        callout_type = m.group(1).strip()
        ln = text[:m.start()].count("\n") + 1
        if callout_type not in VALID_CALLOUT_TYPES:
            issues.append(Issue(f, ln, "error", "callout",
                                f"Unknown callout type: '{callout_type}'"))

    # Check callout-title exists inside each callout
    for m in re.finditer(r'<div class="callout\s+[^"]+">(.{0,500}?)</div>\s*</div>', text, re.DOTALL):
        content = m.group(1)
        ln = text[:m.start()].count("\n") + 1
        if 'class="callout-title"' not in content:
            issues.append(Issue(f, ln, "warning", "callout",
                                "Callout missing callout-title div"))

    return issues


# ============================================================
# CHECK: CODE CAPTIONS
# ============================================================

def check_code_captions(filepath, text, lines) -> List[Issue]:
    """Check code caption format: 'Code Fragment N.N.N:' pattern."""
    issues = []
    f = str(filepath.relative_to(BASE))
    ch_num = get_chapter_num(filepath)

    # Find code blocks followed (or not) by captions
    code_blocks = list(re.finditer(r"</code></pre>", text))

    for cb in code_blocks:
        pos = cb.end()
        ln = text[:pos].count("\n") + 1
        # Look at next 500 chars for a caption
        after = text[pos:pos+500]

        # Skip code-output divs
        after_stripped = after.lstrip()
        if after_stripped.startswith('<div class="code-output">'):
            # Look past the code-output for caption
            output_end = after.find("</div>")
            if output_end > 0:
                after = after[output_end+6:]

        after_stripped = after.lstrip()
        if '<div class="code-caption">' in after_stripped[:200]:
            # Check caption format
            cap_match = re.search(r'Code Fragment\s+([\d\w]+\.[\d\w]+\.[\d\w]+)', after_stripped)
            if not cap_match:
                issues.append(Issue(f, ln, "warning", "code-caption",
                                    "Code caption missing standard numbering 'Code Fragment N.N.N'"))
        else:
            # No caption found near this code block
            issues.append(Issue(f, ln, "info", "code-caption",
                                "Code block without a code-caption div"))

    return issues


# ============================================================
# CHECK: FIGURE CAPTIONS
# ============================================================

def check_figure_captions(filepath, text, lines) -> List[Issue]:
    """Check figure caption format: 'Figure N.N.N:' pattern."""
    issues = []
    f = str(filepath.relative_to(BASE))

    for m in re.finditer(r"<figcaption>(.*?)</figcaption>", text, re.DOTALL):
        content = m.group(1)
        ln = text[:m.start()].count("\n") + 1
        if not re.search(r"Figure\s+[\d\w]+\.[\d\w]+\.[\d\w]+", content):
            issues.append(Issue(f, ln, "warning", "figure-caption",
                                "Figure caption missing standard numbering 'Figure N.N.N'"))

    # Also check diagram-caption divs
    for m in re.finditer(r'class="diagram-caption">(.*?)</div>', text, re.DOTALL):
        content = m.group(1)
        ln = text[:m.start()].count("\n") + 1
        if not re.search(r"Figure\s+[\d\w]+\.[\d\w]+\.[\d\w]+", content):
            issues.append(Issue(f, ln, "warning", "figure-caption",
                                "Diagram caption missing standard numbering 'Figure N.N.N'"))

    return issues


# ============================================================
# CHECK: SECTION HEADING NUMBERING
# ============================================================

def check_heading_sequence(filepath, text, lines) -> List[Issue]:
    """Check h2 headings are sequentially numbered (1, 2, 3, ...)."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    # Extract h2 numbers
    h2_nums = []
    for m in re.finditer(r"<h2[^>]*>\s*(\d+)\.", text):
        num = int(m.group(1))
        ln = text[:m.start()].count("\n") + 1
        h2_nums.append((num, ln))

    if len(h2_nums) < 2:
        return issues

    # Check sequence
    for i in range(1, len(h2_nums)):
        expected = h2_nums[i-1][0] + 1
        actual = h2_nums[i][0]
        if actual != expected:
            issues.append(Issue(f, h2_nums[i][1], "error", "headings",
                                f"H2 numbering gap: expected {expected}, got {actual}"))

    return issues


# ============================================================
# CHECK: FORWARD REFERENCES (concept used before defined)
# ============================================================

def check_forward_references(filepath, text, lines) -> List[Issue]:
    """
    Check if concepts are demonstrated/referenced before they are explained.
    Heuristic: if a code block uses a term that only appears in a heading
    LATER in the same file, flag it.
    """
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    # Build heading index: heading text -> line number
    heading_positions = {}
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", text, re.DOTALL):
        heading_text = re.sub(r"<[^>]+>", "", m.group(1)).strip().lower()
        ln = text[:m.start()].count("\n") + 1
        # Extract key terms from heading (words > 4 chars)
        terms = [w for w in re.findall(r"[a-z]+", heading_text) if len(w) > 4]
        for term in terms:
            if term not in heading_positions:
                heading_positions[term] = ln

    # Find code blocks and check if they use heading terms before the heading
    for m in re.finditer(r"<pre><code[^>]*>(.*?)</code></pre>", text, re.DOTALL):
        code_text = m.group(1).lower()
        code_ln = text[:m.start()].count("\n") + 1

        for term, heading_ln in heading_positions.items():
            # Skip very common terms
            if term in {"pattern", "model", "system", "function", "class",
                        "training", "section", "chapter", "example", "response",
                        "request", "error", "token", "output", "input",
                        "agent", "state", "value", "index", "query", "result",
                        "learning", "method", "implementation", "approach",
                        "calling", "context", "message", "service", "level",
                        "string", "number", "using", "based", "check"}:
                continue
            if term in code_text and code_ln < heading_ln:
                # Code uses this term before the heading that defines it
                issues.append(Issue(f, code_ln, "warning", "forward-ref",
                                    f"Code references '{term}' (line {code_ln}) "
                                    f"before it's defined in heading (line {heading_ln})"))

    return issues


# ============================================================
# CHECK: ACCESSIBILITY
# ============================================================

def check_accessibility(filepath, text, lines) -> List[Issue]:
    """Check alt text on images, aria-labels on SVGs."""
    issues = []
    f = str(filepath.relative_to(BASE))

    # Images without alt
    for m in re.finditer(r"<img\s+([^>]*)>", text):
        attrs = m.group(1)
        ln = text[:m.start()].count("\n") + 1
        if 'alt=' not in attrs:
            issues.append(Issue(f, ln, "error", "accessibility",
                                "Image missing alt attribute"))
        elif 'alt=""' in attrs:
            issues.append(Issue(f, ln, "warning", "accessibility",
                                "Image has empty alt attribute"))

    # SVGs without role="img" or aria-label
    for m in re.finditer(r"<svg\s+([^>]*)>", text):
        attrs = m.group(1)
        ln = text[:m.start()].count("\n") + 1
        if 'role="img"' not in attrs:
            issues.append(Issue(f, ln, "warning", "accessibility",
                                "SVG missing role='img'"))
        if 'aria-label' not in attrs:
            issues.append(Issue(f, ln, "warning", "accessibility",
                                "SVG missing aria-label"))

    return issues


# ============================================================
# CHECK: CROSS-REFERENCES
# ============================================================

def check_cross_refs(filepath, text, lines) -> List[Issue]:
    """Check that cross-ref links point to files that exist."""
    issues = []
    f = str(filepath.relative_to(BASE))

    for m in re.finditer(r'href="([^"#]+)"', text):
        href = m.group(1)
        ln = text[:m.start()].count("\n") + 1

        # Skip external links
        if href.startswith("http") or href.startswith("mailto:"):
            continue

        # Resolve relative path
        target = (filepath.parent / href).resolve()
        if not target.exists():
            issues.append(Issue(f, ln, "error", "cross-ref",
                                f"Broken link: {href}"))

    return issues


# ============================================================
# CHECK: STYLE CONSISTENCY
# ============================================================

def check_style(filepath, text, lines) -> List[Issue]:
    """Check style consistency: em dashes, inline styles, etc."""
    issues = []
    f = str(filepath.relative_to(BASE))

    # Em dashes (user preference: never use)
    for i, line in enumerate(lines):
        if "\u2014" in line or " -- " in line:
            # Skip if inside a code block
            before = "\n".join(lines[:i+1])
            open_pre = before.count("<pre")
            close_pre = before.count("</pre>")
            if open_pre <= close_pre:  # Not inside a <pre> block
                issues.append(Issue(f, i+1, "warning", "style",
                                    "Em dash or double dash found (use commas/semicolons instead)"))

    return issues


# ============================================================
# CHECK: CONCEPT BEFORE DEFINITION
# ============================================================

def check_concept_order(filepath, text, lines) -> List[Issue]:
    """
    Check that major concepts are explained in prose BEFORE code demonstrates them.
    Looks for code blocks that appear before any prose explanation of a heading topic.
    More precise than forward-ref: checks if a heading's first mention in prose
    comes AFTER a code block that uses the term.
    """
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    # Find all h2/h3 headings with their positions
    headings = []
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", text, re.DOTALL):
        clean = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        pos = m.start()
        headings.append((clean, pos))

    # For each heading, check that its concept appears in prose before code
    for heading_text, heading_pos in headings:
        # Get key multi-word phrases from heading (more precise than single words)
        words = re.findall(r"[A-Za-z]+", heading_text)
        if len(words) < 2:
            continue

        # Look for code blocks before this heading
        for cm in re.finditer(r"<pre><code[^>]*>(.*?)</code></pre>", text[:heading_pos], re.DOTALL):
            code = cm.group(1)
            # Check if heading phrase appears as class/function name in code
            # E.g., "CircuitBreaker" in code before "Circuit Breaker" heading
            camel = "".join(w.capitalize() for w in words if len(w) > 2)
            snake = "_".join(w.lower() for w in words if len(w) > 2)
            if camel in code or snake in code:
                code_ln = text[:cm.start()].count("\n") + 1
                heading_ln = text[:heading_pos].count("\n") + 1
                issues.append(Issue(f, code_ln, "warning", "concept-order",
                                    f"Code uses '{camel}' (line {code_ln}) before "
                                    f"heading '{heading_text}' (line {heading_ln})"))

    return issues


# ============================================================
# CHECK: DEPRECATED DIRECTORIES
# ============================================================

def check_deprecated(filepath, text, lines) -> List[Issue]:
    """Flag files in deprecated/duplicate directories."""
    issues = []
    f = str(filepath.relative_to(BASE))

    deprecated = ["part-6-agents-applications", "part-7-production-strategy",
                   "module-17-interpretability", "module-18-embeddings-vector-db",
                   "module-20-conversational-ai"]
    for dep in deprecated:
        if dep in f:
            issues.append(Issue(f, 0, "info", "deprecated",
                                f"File in deprecated directory containing '{dep}'"))
            break

    return issues


# ============================================================
# CHECK: AGENT COUNT CONSISTENCY
# ============================================================

def check_agent_count(filepath, text, lines) -> List[Issue]:
    """Check that agent count references are consistent (should be 42)."""
    issues = []
    f = str(filepath.relative_to(BASE))

    stale_counts = ["46 agent", "46-agent", "46 specialized", "46 production",
                    "47 agent", "47-agent"]
    for sc in stale_counts:
        if sc.lower() in text.lower():
            ln = find_line(lines, sc) or find_line(lines, sc.lower())
            issues.append(Issue(f, ln, "error", "agent-count",
                                f"Stale agent count reference: '{sc}' (should be 42)"))

    return issues


# ============================================================
# CHECK: BIBLIOGRAPHY
# ============================================================

def check_bibliography(filepath, text, lines) -> List[Issue]:
    """Check bibliography section format."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    if 'class="bibliography"' not in text:
        issues.append(Issue(f, 0, "info", "bibliography",
                            "No bibliography section found"))
    else:
        bib_start = find_line(lines, 'class="bibliography"')
        if 'class="bibliography-title"' not in text:
            issues.append(Issue(f, bib_start, "warning", "bibliography",
                                "Bibliography missing bibliography-title div"))
        if 'class="bib-entry-card"' not in text:
            issues.append(Issue(f, bib_start, "warning", "bibliography",
                                "Bibliography has no bib-entry-card entries"))

    return issues


# ============================================================
# CHECK: EXERCISES
# ============================================================

def check_exercises(filepath, text, lines) -> List[Issue]:
    """Check exercise format: level badge, type badge, answer sketch."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    exercises = list(re.finditer(r'callout exercise', text))
    if not exercises:
        issues.append(Issue(f, 0, "info", "exercises", "No exercises found in section"))
        return issues

    for m in re.finditer(r'<div class="callout exercise">(.*?)</div>\s*</div>', text, re.DOTALL):
        content = m.group(1)
        ln = text[:m.start()].count("\n") + 1

        if 'level-badge' not in content:
            issues.append(Issue(f, ln, "warning", "exercises",
                                "Exercise missing level-badge (basic/intermediate/advanced)"))
        if 'exercise-type' not in content:
            issues.append(Issue(f, ln, "warning", "exercises",
                                "Exercise missing exercise-type badge (conceptual/coding)"))

    return issues


# ============================================================
# CHECK: QUIZ / KNOWLEDGE CHECK
# ============================================================

def check_quiz(filepath, text, lines) -> List[Issue]:
    """Check quiz/knowledge-check format."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if not is_section_file(filepath):
        return issues

    if 'class="quiz"' not in text:
        issues.append(Issue(f, 0, "info", "quiz",
                            "No quiz/knowledge-check section found"))

    return issues


# ============================================================
# CHECK: LOADING LAZY ON IMAGES
# ============================================================

def check_lazy_loading(filepath, text, lines) -> List[Issue]:
    """Check that images have loading='lazy' for performance."""
    issues = []
    f = str(filepath.relative_to(BASE))

    for m in re.finditer(r"<img\s+([^>]*)>", text):
        attrs = m.group(1)
        ln = text[:m.start()].count("\n") + 1
        if 'loading="lazy"' not in attrs and 'loading=\'lazy\'' not in attrs:
            issues.append(Issue(f, ln, "info", "lazy-loading",
                                "Image missing loading='lazy' attribute"))

    return issues


# ============================================================
# CHECK: KATEX / PRISM INCLUDES
# ============================================================

def check_head_includes(filepath, text, lines) -> List[Issue]:
    """Check that KaTeX and Prism are included in <head>."""
    issues = []
    f = str(filepath.relative_to(BASE))

    if "katex.min.css" not in text:
        issues.append(Issue(f, 0, "warning", "head-includes",
                            "Missing KaTeX CSS include"))
    if "prism-bundle.min.js" not in text and "prism.min.js" not in text:
        issues.append(Issue(f, 0, "warning", "head-includes",
                            "Missing Prism JS include"))

    return issues


# ============================================================
# MAIN AUDIT RUNNER
# ============================================================

# All checks, tagged by category for filtering
ALL_CHECKS = [
    ("structure", check_structure),
    ("header", check_header),
    ("nav", check_nav),
    ("footer", check_footer),
    ("content", check_section_content),
    ("callout", check_callouts),
    ("code-caption", check_code_captions),
    ("figure-caption", check_figure_captions),
    ("headings", check_heading_sequence),
    ("forward-ref", check_forward_references),
    ("concept-order", check_concept_order),
    ("accessibility", check_accessibility),
    ("cross-ref", check_cross_refs),
    ("style", check_style),
    ("deprecated", check_deprecated),
    ("agent-count", check_agent_count),
    ("bibliography", check_bibliography),
    ("exercises", check_exercises),
    ("quiz", check_quiz),
    ("lazy-loading", check_lazy_loading),
    ("head-includes", check_head_includes),
]


def collect_files(args):
    """Collect HTML files to audit based on args."""
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in str(f) for part in EXCLUDE_DIRS):
            continue
        # Filter by part
        if args.part:
            rel = f.relative_to(BASE)
            if not str(rel).startswith(args.part):
                continue
        # Filter by filename
        if args.file:
            if args.file not in f.name:
                continue
        # Only process section files and chapter indexes (skip pathways, syllabi, etc.)
        if is_section_file(f) or is_chapter_index(f):
            files.append(f)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="HTML conformance audit for LLMCourse")
    parser.add_argument("--part", help="Audit only files in this part directory")
    parser.add_argument("--file", help="Audit only files matching this name")
    parser.add_argument("--check", help="Run only checks matching this category")
    parser.add_argument("--severity", default="info",
                        choices=["info", "warning", "error"],
                        help="Minimum severity to report (default: info)")
    args = parser.parse_args()

    severity_order = {"info": 0, "warning": 1, "error": 2}
    min_sev = severity_order[args.severity]

    files = collect_files(args)
    print(f"Auditing {len(files)} HTML files...\n")

    all_issues = []
    category_counts = defaultdict(lambda: defaultdict(int))

    checks_to_run = ALL_CHECKS
    if args.check:
        checks_to_run = [(cat, fn) for cat, fn in ALL_CHECKS if args.check in cat]

    for filepath in files:
        text, lines_list = read_file(filepath)
        if text is None:
            continue

        for cat, check_fn in checks_to_run:
            try:
                issues = check_fn(filepath, text, lines_list)
                for issue in issues:
                    if severity_order.get(issue.severity, 0) >= min_sev:
                        all_issues.append(issue)
                        category_counts[issue.category][issue.severity] += 1
            except Exception as e:
                rel = filepath.relative_to(BASE)
                print(f"  ERROR running {cat} on {rel}: {e}")

    # Print results grouped by category
    issues_by_cat = defaultdict(list)
    for issue in all_issues:
        issues_by_cat[issue.category].append(issue)

    for cat in sorted(issues_by_cat.keys()):
        cat_issues = issues_by_cat[cat]
        print(f"\n{'='*70}")
        print(f"CATEGORY: {cat.upper()} ({len(cat_issues)} issues)")
        print(f"{'='*70}")

        # Group by severity
        for sev in ["error", "warning", "info"]:
            sev_issues = [i for i in cat_issues if i.severity == sev]
            if not sev_issues:
                continue
            print(f"\n  [{sev.upper()}] ({len(sev_issues)})")
            for issue in sev_issues[:50]:  # Limit output per severity
                line_str = f":{issue.line}" if issue.line else ""
                print(f"    {issue.file}{line_str}")
                print(f"      {issue.message}")
            if len(sev_issues) > 50:
                print(f"    ... and {len(sev_issues) - 50} more")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Files audited: {len(files)}")
    print(f"Total issues: {len(all_issues)}")
    print()

    for cat in sorted(category_counts.keys()):
        counts = category_counts[cat]
        parts = []
        for sev in ["error", "warning", "info"]:
            if counts[sev] > 0:
                parts.append(f"{counts[sev]} {sev}")
        print(f"  {cat:<20} {', '.join(parts)}")

    # Counts by severity
    total_errors = sum(1 for i in all_issues if i.severity == "error")
    total_warnings = sum(1 for i in all_issues if i.severity == "warning")
    total_info = sum(1 for i in all_issues if i.severity == "info")
    print(f"\n  TOTAL: {total_errors} errors, {total_warnings} warnings, {total_info} info")


if __name__ == "__main__":
    main()

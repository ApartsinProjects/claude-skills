"""Check that each module has at least one hands-on lab.

FM.4 promises every chapter includes at least one lab exercise with
runnable code, realistic data, and clear success criteria (30-90 min).

Labs are identified by:
  - <div class="lab"> or <section class="lab"> blocks
  - class="callout exercise" with "Lab" in the title (substantial labs)

This check flags modules (via index.html) that lack any lab content.
"""
import re
from collections import namedtuple
from pathlib import Path

PRIORITY = "P2"
CHECK_ID = "LAB_COVERAGE"
DESCRIPTION = "Module has no hands-on lab (FM.4 promises at least one per chapter)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

LAB_PATTERN = re.compile(r'class="lab[\s"]')


def run(filepath, html, context):
    issues = []
    book_root = context["book_root"]

    # Only check module index files
    if filepath.name != "index.html":
        return []
    if "module-" not in str(filepath):
        return []

    mod_dir = filepath.parent
    section_files = sorted(mod_dir.glob("section-*.html"))
    if not section_files:
        return []

    # Search all sections for lab content
    has_lab = False
    for sf in section_files:
        try:
            sf_html = sf.read_text(encoding="utf-8", errors="replace")
            if LAB_PATTERN.search(sf_html):
                has_lab = True
                break
        except Exception:
            pass

    if not has_lab:
        mod_label = mod_dir.relative_to(book_root)
        issues.append(Issue(
            PRIORITY, CHECK_ID, filepath, 0,
            f"{mod_label} has no hands-on lab (FM.4 promises >= 1 per chapter)"
        ))

    return issues

"""Thorough callout structure checker using div-nesting counter.
Finds callouts where body content is missing or misplaced."""

import re
from pathlib import Path
from collections import defaultdict

BASE = Path(r"E:\Projects\LLMCourse")

def extract_callouts(content, filepath):
    """Extract all callout blocks with proper div nesting."""
    issues = []

    # Find all callout opening tags
    callout_re = re.compile(r'<div\s+class="callout\s+([\w-]+)"[^>]*>')

    for match in callout_re.finditer(content):
        callout_type = match.group(1)
        start = match.start()
        inner_start = match.end()
        line_num = content[:start].count("\n") + 1

        # Count div nesting to find the matching close
        depth = 1
        pos = inner_start
        while depth > 0 and pos < len(content):
            next_open = content.find("<div", pos)
            next_close = content.find("</div>", pos)

            if next_close == -1:
                break

            if next_open != -1 and next_open < next_close:
                depth += 1
                pos = next_open + 4
            else:
                depth -= 1
                if depth == 0:
                    # Found the matching close
                    callout_body = content[inner_start:next_close]

                    # Strip out the callout-title div
                    title_re = re.compile(r'<div\s+class="callout-title"[^>]*>.*?</div>', re.DOTALL)
                    body_without_title = title_re.sub('', callout_body).strip()

                    # Strip HTML tags to get text content
                    text_only = re.sub(r'<[^>]+>', '', body_without_title).strip()

                    # Check for meaningful content
                    has_p = '<p>' in body_without_title or '<p ' in body_without_title
                    has_ul = '<ul>' in body_without_title or '<ul ' in body_without_title
                    has_ol = '<ol>' in body_without_title
                    has_pre = '<pre>' in body_without_title or '<pre ' in body_without_title
                    has_table = '<table' in body_without_title
                    has_content_tags = has_p or has_ul or has_ol or has_pre or has_table

                    if not text_only and not has_content_tags:
                        # Check what comes right after the closing div
                        after = content[next_close+6:next_close+300].strip()
                        issues.append({
                            "line": line_num,
                            "type": callout_type,
                            "issue": "EMPTY_BODY",
                            "after_preview": after[:100],
                            "body_preview": callout_body[:200]
                        })
                    elif len(text_only) < 10 and not has_content_tags:
                        issues.append({
                            "line": line_num,
                            "type": callout_type,
                            "issue": "MINIMAL_BODY",
                            "text": text_only,
                            "body_preview": callout_body[:200]
                        })

                    break
                pos = next_close + 6

    return issues

def check_callout_title_outside(content, filepath):
    """Check if callout-title appears without a proper callout parent."""
    issues = []
    lines = content.split("\n")

    for i, line in enumerate(lines):
        if 'class="callout-title"' in line:
            # Check 10 lines above for a callout parent
            search_back = "\n".join(lines[max(0,i-10):i+1])
            # Must find 'class="callout ' (with space after, to avoid matching callout-title itself)
            if not re.search(r'class="callout\s+\w', search_back):
                issues.append({
                    "line": i + 1,
                    "type": "unknown",
                    "issue": "ORPHAN_TITLE",
                    "text": line.strip()[:100]
                })

    return issues

def check_section_callout_wrapper(content, filepath):
    """Check <section class="callout ..."> which should be <section class="exercises">."""
    issues = []
    for match in re.finditer(r'<section\s+class="callout\s+([\w-]+)"', content):
        line_num = content[:match.start()].count("\n") + 1
        issues.append({
            "line": line_num,
            "type": match.group(1),
            "issue": "SECTION_AS_CALLOUT",
            "text": f'<section class="callout {match.group(1)}"> should not use callout class on section element'
        })

    return issues

# Main scan
print("=" * 70)
print("COMPREHENSIVE CALLOUT STRUCTURE AUDIT")
print("=" * 70)

all_issues = []
stats = defaultdict(int)

html_files = sorted(BASE.rglob("*.html"))
html_files = [f for f in html_files if "_scripts_archive" not in str(f)
              and "node_modules" not in str(f)
              and ".claude" not in str(f)]

for filepath in html_files:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")

        # Count total callouts
        callout_count = len(re.findall(r'<div\s+class="callout\s+[\w-]+"', content))
        stats["total_callouts"] += callout_count

        issues = []
        issues.extend(extract_callouts(content, filepath))
        issues.extend(check_callout_title_outside(content, filepath))
        issues.extend(check_section_callout_wrapper(content, filepath))

        if issues:
            rel = str(filepath.relative_to(BASE))
            for iss in issues:
                all_issues.append({"file": rel, **iss})
                stats[iss["issue"]] += 1

                desc = iss.get("text", iss.get("after_preview", ""))
                print(f"\n  FILE: {rel}:{iss['line']}")
                print(f"  TYPE: {iss['type']}")
                print(f"  ISSUE: {iss['issue']}")
                if desc:
                    print(f"  DETAIL: {desc[:120]}")

    except Exception as e:
        print(f"  ERROR: {filepath}: {e}")

print(f"\n{'=' * 70}")
print(f"SUMMARY")
print(f"{'=' * 70}")
print(f"Total HTML files scanned: {len(html_files)}")
print(f"Total callout boxes found: {stats['total_callouts']}")
print(f"Total issues found: {len(all_issues)}")
for issue_type in ["EMPTY_BODY", "MINIMAL_BODY", "ORPHAN_TITLE", "SECTION_AS_CALLOUT"]:
    if stats[issue_type]:
        print(f"  {issue_type}: {stats[issue_type]}")

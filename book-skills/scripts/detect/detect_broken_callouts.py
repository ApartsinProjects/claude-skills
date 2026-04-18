"""Detect malformed callout boxes where content is outside the callout div.

Patterns detected:
1. Callout div closes immediately after callout-title (empty body)
2. Callout div with text/paragraphs appearing AFTER the closing </div>
3. Callout-title div not properly nested inside callout div
4. Mismatched div nesting causing content to escape
"""

import re
from pathlib import Path
from html.parser import HTMLParser

BASE = Path(r"E:\Projects\LLMCourse")
CALLOUT_TYPES = [
    "big-picture", "key-insight", "note", "warning", "practical-example",
    "fun-note", "research-frontier", "algorithm", "tip", "exercise"
]

class CalloutChecker(HTMLParser):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.issues = []
        self.div_stack = []  # track div nesting
        self.in_callout = False
        self.callout_depth = 0
        self.callout_type = ""
        self.callout_start_line = 0
        self.callout_has_content = False
        self.last_callout_end_line = 0
        self.line_num = 1

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "div":
            classes = attrs_dict.get("class", "")
            # Check if this is a callout div
            is_callout = False
            for ct in CALLOUT_TYPES:
                if f"callout {ct}" in classes or f"callout  {ct}" in classes:
                    is_callout = True
                    self.callout_type = ct
                    break

            if is_callout:
                self.in_callout = True
                self.callout_depth = len(self.div_stack)
                self.callout_start_line = self.getpos()[0]
                self.callout_has_content = False

            self.div_stack.append({"is_callout": is_callout, "line": self.getpos()[0]})

        elif tag in ("p", "ul", "ol", "pre", "h3", "h4", "table", "blockquote"):
            if self.in_callout:
                self.callout_has_content = True

    def handle_endtag(self, tag):
        if tag == "div" and self.div_stack:
            entry = self.div_stack.pop()
            # If we're closing the callout div
            if entry.get("is_callout") and len(self.div_stack) == self.callout_depth:
                if not self.callout_has_content:
                    self.issues.append({
                        "line": self.callout_start_line,
                        "type": self.callout_type,
                        "issue": "EMPTY_CALLOUT",
                        "desc": f"Callout '{self.callout_type}' has no content (only title)"
                    })
                self.in_callout = False
                self.last_callout_end_line = self.getpos()[0]

    def handle_data(self, data):
        if self.in_callout and data.strip():
            self.callout_has_content = True


def check_with_regex(filepath):
    """Regex-based detection for common broken patterns."""
    issues = []
    content = filepath.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    # Pattern 1: callout div that closes right after callout-title
    # <div class="callout TYPE">
    #     <div class="callout-title">...</div>
    # </div>
    # <p>Content that should be inside...</p>
    pattern_empty = re.compile(
        r'<div\s+class="callout\s+(\w[\w-]*)"\s*[^>]*>\s*'
        r'<div\s+class="callout-title">[^<]*</div>\s*'
        r'</div>',
        re.DOTALL
    )

    for match in pattern_empty.finditer(content):
        line_num = content[:match.start()].count("\n") + 1
        callout_type = match.group(1)
        # Check if there's content right after this closing div
        after = content[match.end():match.end()+200].strip()
        if after and not after.startswith("<div") and not after.startswith("<h") and not after.startswith("<nav") and not after.startswith("<footer") and not after.startswith("</"):
            issues.append({
                "line": line_num,
                "type": callout_type,
                "issue": "EMPTY_CALLOUT_CONTENT_AFTER",
                "desc": f"Callout '{callout_type}' closes immediately after title, content follows outside"
            })
        else:
            issues.append({
                "line": line_num,
                "type": callout_type,
                "issue": "EMPTY_CALLOUT",
                "desc": f"Callout '{callout_type}' closes immediately after title (no body content)"
            })

    # Pattern 2: callout-title not inside a callout div
    for i, line in enumerate(lines, 1):
        if 'class="callout-title"' in line:
            # Look backwards for the parent callout div
            context_start = max(0, i - 5)
            context = "\n".join(lines[context_start:i])
            if 'class="callout' not in context.replace('class="callout-title"', ''):
                issues.append({
                    "line": i,
                    "type": "unknown",
                    "issue": "ORPHAN_TITLE",
                    "desc": "callout-title div not inside a callout parent div"
                })

    return issues


def check_div_balance_in_callouts(filepath):
    """Check that div nesting is balanced within callout boxes."""
    issues = []
    content = filepath.read_text(encoding="utf-8", errors="replace")

    # Find all callout blocks
    callout_pattern = re.compile(
        r'(<div\s+class="callout\s+[\w-]+"\s*[^>]*>)(.*?)(</div>)',
        re.DOTALL
    )

    # For each potential callout, count div opens vs closes inside
    pos = 0
    while pos < len(content):
        # Find next callout opening
        match = re.search(r'<div\s+class="callout\s+([\w-]+)"\s*[^>]*>', content[pos:])
        if not match:
            break

        start = pos + match.start()
        callout_type = match.group(1)
        line_num = content[:start].count("\n") + 1

        # Now find the matching closing div by counting nesting
        inner_start = start + len(match.group(0))
        depth = 1
        scan_pos = inner_start
        while depth > 0 and scan_pos < len(content):
            next_open = content.find("<div", scan_pos)
            next_close = content.find("</div>", scan_pos)

            if next_close == -1:
                break

            if next_open != -1 and next_open < next_close:
                depth += 1
                scan_pos = next_open + 4
            else:
                depth -= 1
                if depth == 0:
                    # This is the closing div of the callout
                    callout_content = content[inner_start:next_close]
                    # Check if there's meaningful content
                    stripped = re.sub(r'<[^>]+>', '', callout_content).strip()
                    # Remove just the callout-title text
                    stripped = re.sub(r'^\s*[\w\s:&;]+\s*$', '', stripped, count=1).strip()
                    if not stripped and len(callout_content.strip()) < 100:
                        # Very little content
                        after_close = content[next_close+6:next_close+300].strip()
                        if after_close.startswith("<p>") or after_close.startswith("<ul>"):
                            issues.append({
                                "line": line_num,
                                "type": callout_type,
                                "issue": "LIKELY_ESCAPED_CONTENT",
                                "desc": f"Callout '{callout_type}' has minimal content, <p>/<ul> follows immediately after"
                            })
                scan_pos = next_close + 6

        pos = start + 1

    return issues


# Main scan
print("Scanning all HTML files for broken callout structures...\n")

all_issues = []
html_files = sorted(BASE.rglob("*.html"))
html_files = [f for f in html_files if "_scripts_archive" not in str(f) and "node_modules" not in str(f)]

for filepath in html_files:
    try:
        issues = check_with_regex(filepath)
        issues2 = check_div_balance_in_callouts(filepath)
        all_found = issues + issues2

        # Deduplicate by line number
        seen_lines = set()
        unique = []
        for iss in all_found:
            key = (iss["line"], iss["issue"])
            if key not in seen_lines:
                seen_lines.add(key)
                unique.append(iss)

        if unique:
            rel = filepath.relative_to(BASE)
            for iss in unique:
                all_issues.append({"file": str(rel), **iss})
                print(f"  {rel}:{iss['line']} [{iss['issue']}] {iss['desc']}")
    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")

print(f"\n{'='*60}")
print(f"Total issues found: {len(all_issues)}")

# Group by issue type
from collections import Counter
type_counts = Counter(iss["issue"] for iss in all_issues)
for issue_type, count in type_counts.most_common():
    print(f"  {issue_type}: {count}")

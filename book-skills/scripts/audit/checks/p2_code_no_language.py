"""Check for pre/code blocks missing a language class for syntax highlighting."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "CODE_NO_LANGUAGE"
DESCRIPTION = "<pre><code> block without language-* class (no syntax highlighting)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Match <pre><code> or <pre><code class="..."> where class has no language- prefix
PRE_CODE_RE = re.compile(r'<pre>\s*<code\b([^>]*)>', re.IGNORECASE)
LANG_CLASS_RE = re.compile(r'class="[^"]*\blanguage-\w+')

# Exclude algorithm/pseudocode blocks (typically have algo-line-keyword spans)
ALGO_RE = re.compile(r'algo-line-keyword|pseudocode|algorithm', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    for i, line in enumerate(lines, 1):
        for m in PRE_CODE_RE.finditer(line):
            attrs = m.group(1)
            if LANG_CLASS_RE.search(attrs):
                continue
            # Check a window around the match for algorithm indicators
            context_window = "\n".join(lines[max(0, i - 3):min(len(lines), i + 5)])
            if ALGO_RE.search(context_window):
                continue
            # Get a preview of code content
            start = m.end()
            preview = html[html.find(m.group(), max(0, sum(len(l) + 1 for l in lines[:i-1]))):]
            preview = preview[len(m.group()):len(m.group()) + 60]
            preview = re.sub(r'<[^>]+>', '', preview).strip()[:40]
            issues.append(Issue(
                PRIORITY, CHECK_ID, filepath, i,
                f'<pre><code> without language class: "{preview}..."',
            ))
    return issues

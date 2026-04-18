"""Check for callout divs where the CSS class clearly contradicts the title text."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "CALLOUT_TYPE_MISMATCH"
DESCRIPTION = "Callout CSS class contradicts its title text (e.g. fun-note with Hands-On title)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Only flag when the title text clearly belongs to a DIFFERENT callout type.
# key: (class_suffix, title_lower) pairs that are definitely wrong.
# We detect when a title matches a known callout type keyword but the class is different.
TITLE_TO_EXPECTED_CLASS = {
    "fun fact": "fun-note",
    "hands-on": "hands-on",
    "key insight": "key-insight",
    "big picture": "big-picture",
    "warning": "warning",
    "caution": "warning",
    "algorithm": "algorithm",
    "library shortcut": "library-shortcut",
}

CALLOUT_RE = re.compile(r'<div\s+class="callout\s+([^"]+)"', re.IGNORECASE)
TITLE_RE = re.compile(r'<div\s+class="callout-title"[^>]*>(.*?)</div>', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    pending_class = None
    pending_line = None

    for i, line in enumerate(lines, 1):
        cm = CALLOUT_RE.search(line)
        if cm:
            pending_class = cm.group(1).strip()
            pending_line = i

        tm = TITLE_RE.search(line)
        if tm and pending_class:
            title_text = re.sub(r'<[^>]+>', '', tm.group(1)).strip().lower()

            # Check if the title is a known callout type keyword
            # that does not match the current class
            if title_text in TITLE_TO_EXPECTED_CLASS:
                expected_class = TITLE_TO_EXPECTED_CLASS[title_text]
                if pending_class != expected_class:
                    issues.append(Issue(
                        PRIORITY, CHECK_ID, filepath, pending_line,
                        f'Callout class "callout {pending_class}" has title '
                        f'"{title_text}" (expected class "callout {expected_class}")'
                    ))

            pending_class = None
            pending_line = None

    return issues

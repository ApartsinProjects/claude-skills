"""Check for SVG aria-label attributes that appear truncated (end mid-sentence)."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "SVG_ARIA_TRUNCATED"
DESCRIPTION = "SVG aria-label appears truncated (cut off mid-sentence)"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

SVG_ARIA_RE = re.compile(
    r'<svg\b[^>]*\baria-label=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _looks_truncated(label):
    """Heuristic: label is truncated if it ends mid-word or with certain patterns."""
    label = label.strip()
    if not label:
        return False

    # Too short to judge
    if len(label) < 20:
        return False

    # Ends with a common truncation indicator
    last_char = label[-1]
    # Normal endings: period, question mark, closing paren, etc.
    if last_char in '.?!:)]:':
        return False

    # Ends with a lowercase letter or comma followed by nothing (mid-sentence)
    if last_char == ',':
        return True

    # Check if it ends with a common partial word or preposition
    trailing = label.split()[-1].lower() if label.split() else ""
    TRUNCATION_WORDS = {
        "the", "a", "an", "and", "or", "of", "in", "to", "for",
        "with", "from", "by", "on", "at", "as", "is", "are",
    }
    if trailing in TRUNCATION_WORDS:
        return True

    # Long label that doesn't end with a sentence-ending character
    # and the label itself looks like a sentence (has spaces, starts with cap)
    if len(label) > 60 and label[0].isupper() and ' ' in label:
        # If it doesn't end with a word that could be a final noun/verb, likely truncated
        if last_char.islower() and not label.endswith(')'):
            return True

    return False


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in SVG_ARIA_RE.finditer(line):
            label = m.group(1).strip()
            if _looks_truncated(label):
                display = label[-60:] if len(label) > 60 else label
                issues.append(Issue(
                    PRIORITY, CHECK_ID, filepath, i,
                    f'SVG aria-label appears truncated: "...{display}"',
                ))
    return issues

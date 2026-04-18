"""Check for vague or context-free headings that rely on parent context."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "VAGUE_HEADING"
DESCRIPTION = "Heading is too generic to be meaningful on its own"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Patterns that are vague without additional context
VAGUE_PATTERNS = [
    (re.compile(r'^The Algorithm$', re.IGNORECASE), "Which algorithm? Include the name"),
    (re.compile(r'^The Algorithm in Detail$', re.IGNORECASE), "Which algorithm? Include the name"),
    (re.compile(r'^How It Works$', re.IGNORECASE), "What is 'it'? Include the subject"),
    (re.compile(r'^Implementation$', re.IGNORECASE), "Implementation of what? Include the subject"),
    (re.compile(r'^The Implementation$', re.IGNORECASE), "Implementation of what? Include the subject"),
    (re.compile(r'^Example$', re.IGNORECASE), "Example of what? Include the topic"),
    (re.compile(r'^An Example$', re.IGNORECASE), "Example of what? Include the topic"),
    (re.compile(r'^Details$', re.IGNORECASE), "Details of what?"),
    (re.compile(r'^More Details$', re.IGNORECASE), "Details of what?"),
    (re.compile(r'^The Approach$', re.IGNORECASE), "Which approach?"),
    (re.compile(r'^The Model$', re.IGNORECASE), "Which model?"),
    (re.compile(r'^The Architecture$', re.IGNORECASE), "Which architecture?"),
    (re.compile(r'^The Method$', re.IGNORECASE), "Which method?"),
    (re.compile(r'^Discussion$', re.IGNORECASE), "Discussion of what?"),
    (re.compile(r'^Results$', re.IGNORECASE), "Results of what?"),
    (re.compile(r'^The Process$', re.IGNORECASE), "Which process?"),
    (re.compile(r'^The Pipeline$', re.IGNORECASE), "Which pipeline?"),
    (re.compile(r'^The Framework$', re.IGNORECASE), "Which framework?"),
    (re.compile(r'^Overview$', re.IGNORECASE), "Overview of what?"),
    # "Putting It All Together" without colon/subtitle
    (re.compile(r'^(?:\d+\.\s*)?Putting It All Together$', re.IGNORECASE),
     "Add subtitle specifying what is being combined"),
]

HEADING_RE = re.compile(r'<h[23][^>]*>(.*?)</h[23]>', re.DOTALL)


def run(filepath, html, context):
    issues = []
    for i, line in enumerate(html.split("\n"), 1):
        for m in HEADING_RE.finditer(line):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            # Strip leading numbers like "2. "
            clean = re.sub(r'^\d+\.\s*', '', text)
            for pattern, suggestion in VAGUE_PATTERNS:
                if pattern.match(clean):
                    issues.append(Issue(PRIORITY, CHECK_ID, filepath, i,
                        f'Vague heading: "{text}" ({suggestion})'))
                    break
    return issues

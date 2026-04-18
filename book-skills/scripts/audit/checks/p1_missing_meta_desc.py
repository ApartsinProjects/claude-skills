"""Check for missing <meta name="description"> tag in <head>."""
import re
from collections import namedtuple

PRIORITY = "P1"
CHECK_ID = "MISSING_META_DESC"
DESCRIPTION = "Page is missing <meta name=\"description\"> in <head>"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

HEAD_RE = re.compile(r'<head\b[^>]*>(.*?)</head>', re.DOTALL | re.IGNORECASE)
META_DESC_RE = re.compile(r'<meta\s+name=["\']description["\']', re.IGNORECASE)


def run(filepath, html, context):
    issues = []

    # Skip HTML fragments (no <head> expected)
    if "_lab_fragments" in str(filepath).replace("\\", "/"):
        return issues

    head_match = HEAD_RE.search(html)
    if not head_match:
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, 1,
            "No <head> section found"))
        return issues

    head_content = head_match.group(1)
    if not META_DESC_RE.search(head_content):
        # Find the line number of <head>
        head_line = html[:head_match.start()].count("\n") + 1
        issues.append(Issue(PRIORITY, CHECK_ID, filepath, head_line,
            "Missing <meta name=\"description\"> in <head>"))

    return issues

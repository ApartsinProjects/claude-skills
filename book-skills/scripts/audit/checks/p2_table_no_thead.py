"""Check for <table> elements that have no <thead> section."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "TABLE_NO_THEAD"
DESCRIPTION = "<table> element is missing a <thead> section"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

TABLE_RE = re.compile(r'<table\b[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
THEAD_RE = re.compile(r'<thead\b', re.IGNORECASE)
TABLE_OPEN_RE = re.compile(r'<table\b[^>]*>', re.IGNORECASE)


def run(filepath, html, context):
    issues = []
    for m in TABLE_RE.finditer(html):
        table_content = m.group(1)
        if not THEAD_RE.search(table_content):
            # Find line number of the <table> opening tag
            line_num = html[:m.start()].count("\n") + 1
            # Try to get a class or id for context
            open_tag = TABLE_OPEN_RE.match(m.group(0))
            tag_text = open_tag.group(0) if open_tag else "<table>"
            preview = tag_text[:60]
            issues.append(Issue(PRIORITY, CHECK_ID, filepath, line_num,
                f'Table without <thead>: {preview}'))
    return issues

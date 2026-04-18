"""Check for hardcoded color/size values in <style> blocks that should use CSS variables."""
import re
from collections import namedtuple, defaultdict

PRIORITY = "P2"
CHECK_ID = "HARDCODED_STYLE"
DESCRIPTION = "Inline <style> block uses hardcoded color/size instead of CSS variable"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Known CSS variables that should be used instead of hardcoded values
VARIABLE_MAP = {
    "#1a1a2e": "var(--primary)",
    "#0f3460": "var(--accent)",
    "#e94560": "var(--highlight)",
    "#16213e": "var(--primary) or similar dark navy",
}

STYLE_BLOCK_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.DOTALL | re.IGNORECASE)
HEX_COLOR_RE = re.compile(r'#[0-9a-fA-F]{3,8}\b')

# Exclude colors that are clearly one-off design choices (grays, whites, blacks)
SKIP_COLORS = {
    "#fff", "#ffffff", "#000", "#000000",
    "#f0f0f0", "#f4f4f4", "#f8f8f8", "#fafafa",
    "#e8e8e8", "#eee", "#eeeeee",
    "#ddd", "#dddddd", "#ccc", "#cccccc",
    "#999", "#888", "#777", "#666", "#555", "#444", "#333", "#222", "#111",
    "#f4f7fa", "#e0e0e0", "#b0bec5",
}

# Cross-file tracking for repeated style blocks
_style_blocks = []


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")

    for block_match in STYLE_BLOCK_RE.finditer(html):
        block = block_match.group(1)
        block_start = html[:block_match.start()].count("\n") + 1

        for color_match in HEX_COLOR_RE.finditer(block):
            color = color_match.group(0).lower()
            if color in SKIP_COLORS:
                continue

            # Check if it matches a known variable
            if color in VARIABLE_MAP:
                line_offset = block[:color_match.start()].count("\n")
                issues.append(Issue(PRIORITY, CHECK_ID, filepath,
                    block_start + line_offset,
                    f'Hardcoded {color} in <style> block; use {VARIABLE_MAP[color]}'))

        # Track for cross-file analysis
        _style_blocks.append((filepath, block))

    return issues

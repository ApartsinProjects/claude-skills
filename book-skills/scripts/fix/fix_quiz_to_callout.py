#!/usr/bin/env python3
"""Convert quiz/quiz-box divs to callout self-check format.

Before:
    <div class="quiz">
        <h3>&#x2753; Section Quiz</h3>    (or "Section N.N Quiz", etc.)
        <p class="quiz-question">1. ...</p>
        <details open>
            <summary>Show Answer</summary>
            <div class="answer">...</div>
        </details>
        ...
    </div>

After:
    <div class="callout self-check">
        <div class="callout-title">Self-Check</div>
        <p class="quiz-question">1. ...</p>
        <details>
            <summary>Show Answer</summary>
            <div class="answer">...</div>
        </details>
        ...
    </div>

Also converts <div class="quiz-question"> to <p class="quiz-question">.
Removes "details open" -> "details" (answers hidden by default).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", "_archive", "agents", "vendor"}


def should_skip(filepath):
    return any(s in filepath.parts for s in SKIP_DIRS)


def fix_file(filepath):
    text = filepath.read_text(encoding="utf-8")
    original = text
    changes = []

    # 1. Replace <div class="quiz"> and <div class="quiz-box"> with <div class="callout self-check">
    for old_class in ('quiz-box', 'quiz'):
        pattern = f'<div class="{old_class}">'
        if pattern in text:
            text = text.replace(pattern, '<div class="callout self-check">')
            changes.append(f'  class="{old_class}" -> "callout self-check"')

    # 2. Replace quiz h3 headers with callout-title div
    #    Patterns: <h3>&#x2753; Section Quiz</h3>
    #              <h3>Section N.N Quiz</h3>
    #              <h3>📝 Section Quiz</h3>
    #              <h3>Check Your Understanding</h3>
    h3_pattern = re.compile(
        r'<h3>[^<]*(?:Quiz|Check Your Understanding|Self[- ]Check)[^<]*</h3>',
        re.IGNORECASE
    )
    h3_matches = h3_pattern.findall(text)
    if h3_matches:
        text = h3_pattern.sub('<div class="callout-title">Self-Check</div>', text)
        changes.append(f'  Replaced {len(h3_matches)} quiz h3 -> callout-title')

    # 3. Convert <div class="quiz-question"> to <p class="quiz-question">
    #    Need to also fix closing </div> for these
    div_q_pattern = re.compile(
        r'<div class="quiz-question">(.*?)</div>',
        re.DOTALL
    )
    div_q_matches = div_q_pattern.findall(text)
    if div_q_matches:
        text = div_q_pattern.sub(r'<p class="quiz-question">\1</p>', text)
        changes.append(f'  Converted {len(div_q_matches)} div.quiz-question -> p.quiz-question')

    # 4. Remove "open" from <details open> inside self-check callouts
    #    (answers should be hidden by default)
    details_open = '<details open>'
    if details_open in text:
        count = text.count(details_open)
        text = text.replace(details_open, '<details>')
        changes.append(f'  Removed "open" from {count} <details> tags')

    if text != original:
        filepath.write_text(text, encoding="utf-8")
        return changes
    return None


def main():
    fixed = 0
    total_changes = 0

    for html_file in sorted(ROOT.rglob("*.html")):
        if should_skip(html_file):
            continue
        # Only process files that have quiz content
        try:
            content = html_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'class="quiz' not in content:
            continue

        changes = fix_file(html_file)
        if changes:
            rel = html_file.relative_to(ROOT)
            print(f"Fixed: {rel}")
            for c in changes:
                print(c)
            fixed += 1
            total_changes += len(changes)

    print(f"\n{'=' * 60}")
    print(f"Fixed {fixed} files ({total_changes} changes)")


if __name__ == "__main__":
    main()

"""Fix stacked code-caption divs: consecutive captions with no <pre> between them.

Root causes handled:
  1. Caption displaced from its code block (match caption to nearby uncaptioned <pre>)
  2. Missing library shortcut code block (mark with TODO comment)
  3. Duplicate or ambiguous captions (mark with FIXME for manual review)

Also fixes letter-suffix numbering (e.g., 5a, 5b) by renumbering to next integer.

Conservative approach: only relocate captions when the match is unambiguous.
Mark uncertain cases for manual review rather than guessing.
"""

import re
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_caption_text(line):
    """Extract the visible text content from a code-caption div line."""
    # Remove HTML tags to get plain text
    text = re.sub(r'<[^>]+>', '', line)
    return text.strip()


def extract_caption_label(line):
    """Extract the Code Fragment label (e.g., '14.1.2') from a caption line."""
    m = re.search(r'Code Fragment ([\d.]+[a-zA-Z]?)', line)
    return m.group(1) if m else None


def extract_pre_content(lines, pre_start):
    """Extract the text content of a <pre> block starting at pre_start."""
    text_lines = []
    for j in range(pre_start, min(pre_start + 200, len(lines))):
        text_lines.append(lines[j])
        if '</pre>' in lines[j]:
            break
    raw = '\n'.join(text_lines)
    # Strip HTML tags
    return re.sub(r'<[^>]+>', '', raw)


def is_caption_line(line):
    return 'class="code-caption"' in line


def is_pre_line(line):
    return '<pre' in line.lower()


def caption_mentions_shortcut(line):
    """Check if a caption mentions 'shortcut', 'library', 'alternative', or 'local'."""
    text = extract_caption_text(line).lower()
    keywords = ['shortcut', 'library shortcut', 'local alternative',
                'replaces the', 'open-source model', 'local embedding',
                'alternative approach', 'alternative implementation']
    return any(kw in text for kw in keywords)


def word_overlap_score(caption_text, code_text):
    """Compute a simple word overlap score between caption and code content."""
    # Extract meaningful words (length >= 3, not common stopwords)
    stopwords = {'the', 'and', 'for', 'this', 'that', 'with', 'from', 'each',
                 'how', 'into', 'uses', 'used', 'using', 'which', 'also',
                 'can', 'are', 'was', 'were', 'has', 'have', 'been', 'its',
                 'will', 'not', 'all', 'any', 'but', 'more', 'than', 'then',
                 'code', 'fragment', 'snippet', 'demonstrates', 'approach',
                 'implementation', 'study', 'understand', 'component',
                 'contributes', 'overall', 'workflow', 'function', 'class',
                 'def', 'import', 'return', 'self', 'print', 'none',
                 'true', 'false'}
    def meaningful_words(text):
        words = set(re.findall(r'[a-zA-Z_]\w{2,}', text.lower()))
        return words - stopwords
    cap_words = meaningful_words(caption_text)
    code_words = meaningful_words(code_text)
    if not cap_words:
        return 0
    return len(cap_words & code_words) / len(cap_words)


# ---------------------------------------------------------------------------
# Element parsing: build a list of elements with type, line range, content
# ---------------------------------------------------------------------------

def parse_elements(lines):
    """Parse lines into a sequence of elements: 'caption', 'pre', 'other'.

    Each element: {'type': str, 'start': int, 'end': int, 'lines': [str]}
    Line numbers are 0-based indices.
    """
    elements = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if is_caption_line(line):
            # Caption may be single-line or multi-line
            start = i
            if '</div>' in line:
                end = i
            else:
                end = i
                for j in range(i + 1, min(i + 20, len(lines))):
                    end = j
                    if '</div>' in lines[j]:
                        break
            elements.append({
                'type': 'caption',
                'start': start,
                'end': end,
                'lines': lines[start:end + 1],
            })
            i = end + 1

        elif is_pre_line(line):
            start = i
            end = i
            if '</pre>' not in line:
                for j in range(i + 1, min(i + 500, len(lines))):
                    end = j
                    if '</pre>' in lines[j]:
                        break
            elements.append({
                'type': 'pre',
                'start': start,
                'end': end,
                'lines': lines[start:end + 1],
            })
            i = end + 1

        else:
            # Accumulate non-caption, non-pre lines as 'other'
            start = i
            end = i
            i += 1
            while i < len(lines) and not is_caption_line(lines[i]) and not is_pre_line(lines[i]):
                end = i
                i += 1
            elements.append({
                'type': 'other',
                'start': start,
                'end': end,
                'lines': lines[start:end + 1],
            })

    return elements


# ---------------------------------------------------------------------------
# Stacked caption detection
# ---------------------------------------------------------------------------

def find_stacked_groups(elements):
    """Find groups of consecutive caption elements (no pre between them).

    Returns list of groups. Each group is a list of element indices.
    Blank 'other' lines between captions still count as stacked.
    """
    groups = []
    current_group = []

    for idx, el in enumerate(elements):
        if el['type'] == 'caption':
            if not current_group:
                current_group = [idx]
            else:
                current_group.append(idx)
        elif el['type'] == 'pre':
            # A pre block breaks the stack
            if len(current_group) >= 2:
                groups.append(current_group)
            current_group = []
        else:
            # 'other' element: check if it is just whitespace/blank lines
            text = '\n'.join(el['lines']).strip()
            # If non-trivial content, break the group
            if text and not all(
                l.strip() == '' or l.strip().startswith('<!--') for l in el['lines']
            ):
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = []
            # If trivial (blank/comment), keep accumulating

    if len(current_group) >= 2:
        groups.append(current_group)

    return groups


# ---------------------------------------------------------------------------
# Fix strategies
# ---------------------------------------------------------------------------

def find_uncaptioned_pre_blocks(elements):
    """Find pre blocks that have no caption immediately after them.

    Returns dict: element_index -> pre element.
    A pre is 'captioned' if the next non-trivial element after it is a caption.
    """
    uncaptioned = {}
    for idx, el in enumerate(elements):
        if el['type'] != 'pre':
            continue

        # Look forward for the next non-trivial element
        has_caption_after = False
        # Also check for code-output div right after
        j = idx + 1
        while j < len(elements):
            if elements[j]['type'] == 'caption':
                has_caption_after = True
                break
            elif elements[j]['type'] == 'pre':
                break
            elif elements[j]['type'] == 'other':
                text = '\n'.join(elements[j]['lines']).strip()
                # code-output divs or blank lines are OK to skip
                if not text or 'class="code-output"' in text:
                    j += 1
                    continue
                else:
                    break
            else:
                break
        if not has_caption_after:
            uncaptioned[idx] = el

    return uncaptioned


def try_match_caption_to_pre(caption_el, uncaptioned_pres, all_lines):
    """Try to match a single caption to one of the uncaptioned pre blocks.

    Returns the element index of the best match, or None.
    """
    caption_text = extract_caption_text('\n'.join(caption_el['lines']))

    best_idx = None
    best_score = 0.0

    for pre_idx, pre_el in uncaptioned_pres.items():
        pre_text = '\n'.join(pre_el['lines'])
        pre_content = re.sub(r'<[^>]+>', '', pre_text)
        score = word_overlap_score(caption_text, pre_content)

        if score > best_score:
            best_score = score
            best_idx = pre_idx

    # Only return a match if the score is meaningfully above zero
    if best_score >= 0.15 and best_idx is not None:
        return best_idx
    return None


# ---------------------------------------------------------------------------
# Letter suffix renumbering
# ---------------------------------------------------------------------------

def fix_letter_suffixes_in_file(content):
    """Rename letter-suffix fragment labels to use the next available integer.

    E.g., if a file has 5, 5a, 6 then 5a becomes 6 and old 6 becomes 7.
    Works within each section prefix (e.g., 14.1.X, 14.2.X are independent).
    """
    lines = content.split('\n')

    # First pass: collect all caption labels by section prefix
    # Section prefix = everything before the last dot-number (e.g., "14.1" from "14.1.3")
    label_map = {}  # maps (line_index, old_label) for tracking
    captions_by_prefix = {}  # prefix -> [(line_idx, full_label, has_suffix)]

    for i, line in enumerate(lines):
        if 'class="code-caption"' not in line:
            continue
        label = extract_caption_label(line)
        if label is None:
            continue

        # Determine if this label has a letter suffix
        has_suffix = bool(re.search(r'\d+[a-zA-Z]$', label))

        # Get the section prefix (everything up to and including the second-to-last segment)
        parts = label.split('.')
        if len(parts) >= 2:
            prefix = '.'.join(parts[:-1])
            local_num = parts[-1]
        else:
            prefix = ''
            local_num = parts[0]

        if prefix not in captions_by_prefix:
            captions_by_prefix[prefix] = []
        captions_by_prefix[prefix].append((i, label, local_num, has_suffix))

    # For each prefix that has letter suffixes, compute new numbering
    changes = {}  # old_label -> new_label

    for prefix, entries in captions_by_prefix.items():
        # Check if any entry has a suffix
        if not any(has_suffix for _, _, _, has_suffix in entries):
            continue

        # Sort by line order (they should already be in order, but be safe)
        entries.sort(key=lambda x: x[0])

        # Build the new numbering: assign sequential integers
        next_num = None
        for i, (line_idx, full_label, local_num, has_suffix) in enumerate(entries):
            # Extract the base number
            base_match = re.match(r'(\d+)', local_num)
            if not base_match:
                continue
            base_num = int(base_match.group(1))

            if has_suffix:
                # This needs renumbering. Find the next available integer.
                # Look at what the previous entry's new number was
                if next_num is None:
                    next_num = base_num + 1
                new_label = f"{prefix}.{next_num}" if prefix else str(next_num)
                changes[full_label] = new_label
                next_num += 1
            else:
                # Non-suffix label. If we have been renumbering, we may need
                # to bump this one too if its number collides
                if next_num is not None and base_num < next_num:
                    new_label = f"{prefix}.{next_num}" if prefix else str(next_num)
                    changes[full_label] = new_label
                    next_num += 1
                elif next_num is not None:
                    next_num = base_num + 1
                else:
                    next_num = base_num + 1

    # Apply changes to content
    if changes:
        for old_label, new_label in changes.items():
            # Replace in caption divs and in cross-references
            old_escaped = re.escape(old_label)
            # Replace "Code Fragment X.Y.Za" with "Code Fragment X.Y.Z+1"
            content = re.sub(
                rf'(Code Fragment\s+){old_escaped}\b',
                rf'\g<1>{new_label}',
                content
            )

    return content, changes


# ---------------------------------------------------------------------------
# Main fix logic per file
# ---------------------------------------------------------------------------

def fix_file(filepath):
    """Fix stacked captions in a single file. Returns (changed: bool, report: list[str])."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    original = content
    report = []

    # Phase 1: Fix letter suffixes first (this changes labels but not structure)
    content, suffix_changes = fix_letter_suffixes_in_file(content)
    if suffix_changes:
        for old, new in suffix_changes.items():
            report.append(f"  RENAME: Code Fragment {old} -> {new}")

    # Phase 2: Fix stacked captions
    lines = content.split('\n')
    elements = parse_elements(lines)
    stacked_groups = find_stacked_groups(elements)

    if not stacked_groups:
        # No stacked captions, but may have had suffix changes
        if content != original:
            with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            return True, report
        return False, report

    uncaptioned_pres = find_uncaptioned_pre_blocks(elements)

    # Process each stacked group
    # We need to track which lines to remove and where to insert them
    relocations = []  # (caption_element_idx, target_pre_element_idx)
    todo_marks = []   # caption_element_idx values to mark with TODO
    fixme_marks = []  # caption_element_idx values to mark with FIXME

    for group in stacked_groups:
        # group is a list of element indices, all captions
        caption_els = [(idx, elements[idx]) for idx in group]

        # Find the pre block immediately before this group (the "owning" pre)
        first_caption_idx = group[0]
        owning_pre_idx = None
        for search_idx in range(first_caption_idx - 1, -1, -1):
            if elements[search_idx]['type'] == 'pre':
                owning_pre_idx = search_idx
                break
            elif elements[search_idx]['type'] == 'other':
                text = '\n'.join(elements[search_idx]['lines']).strip()
                if text and 'class="code-output"' not in text:
                    break
                continue
            else:
                break

        # The first caption in the group likely belongs to the owning pre block.
        # The remaining captions are the "extra" ones that need fixing.
        # But we should verify: does the first caption describe the owning pre?

        if owning_pre_idx is not None:
            # First caption stays with the owning pre. Process the rest.
            extra_captions = caption_els[1:]
        else:
            # No owning pre found, all captions are orphaned
            extra_captions = caption_els

        for cap_idx, cap_el in extra_captions:
            cap_text = extract_caption_text('\n'.join(cap_el['lines']))

            # Strategy 1: Try to match to an uncaptioned pre block
            match_pre_idx = try_match_caption_to_pre(cap_el, uncaptioned_pres, lines)

            if match_pre_idx is not None:
                relocations.append((cap_idx, match_pre_idx))
                # Remove from uncaptioned pool so we do not double-assign
                del uncaptioned_pres[match_pre_idx]
                label = extract_caption_label('\n'.join(cap_el['lines'])) or '?'
                report.append(f"  MOVE: Code Fragment {label} -> after pre at line {elements[match_pre_idx]['start'] + 1}")
                continue

            # Strategy 2: If caption mentions "shortcut"/"library"/"local", mark with TODO
            if caption_mentions_shortcut('\n'.join(cap_el['lines'])):
                todo_marks.append(cap_idx)
                label = extract_caption_label('\n'.join(cap_el['lines'])) or '?'
                report.append(f"  TODO: Code Fragment {label} (library shortcut, no code block)")
                continue

            # Strategy 3: Fallback, mark with FIXME
            fixme_marks.append(cap_idx)
            label = extract_caption_label('\n'.join(cap_el['lines'])) or '?'
            report.append(f"  FIXME: Code Fragment {label} (needs manual review)")

    # Apply changes: build new lines list
    # We need to:
    # 1. Remove relocated captions from their original positions
    # 2. Insert them after their target pre blocks (after any code-output)
    # 3. Add TODO/FIXME comments

    # First, mark which line ranges to skip (relocated captions)
    skip_ranges = set()
    for cap_idx, _ in relocations:
        el = elements[cap_idx]
        for ln in range(el['start'], el['end'] + 1):
            skip_ranges.add(ln)

    # Build insertion map: target_line -> list of caption line groups to insert
    # Insert after the pre block (and any code-output after it)
    insertions = {}  # line_number (insert after this line) -> [lines_to_insert]
    for cap_idx, pre_idx in relocations:
        cap_el = elements[cap_idx]
        pre_el = elements[pre_idx]
        cap_lines = cap_el['lines']

        # Find the insertion point: after </pre> and any code-output div
        insert_after = pre_el['end']

        # Check if there is a code-output div right after
        next_idx = pre_idx + 1
        while next_idx < len(elements):
            if elements[next_idx]['type'] == 'other':
                text = '\n'.join(elements[next_idx]['lines']).strip()
                if 'class="code-output"' in text:
                    insert_after = elements[next_idx]['end']
                    next_idx += 1
                    continue
                elif not text:
                    # blank line, skip it but keep checking
                    next_idx += 1
                    continue
                else:
                    break
            else:
                break

        if insert_after not in insertions:
            insertions[insert_after] = []
        insertions[insert_after].extend(cap_lines)

    # Also remove blank lines that were between stacked captions in a group
    # (lines that are now orphaned between the remaining caption and the removed ones)

    # Build new content
    new_lines = []
    for i, line in enumerate(lines):
        if i in skip_ranges:
            # Also skip blank lines immediately around removed captions
            # (we will handle spacing at insertion point)
            continue
        new_lines.append(line)

        if i in insertions:
            new_lines.extend(insertions[i])

    # Add TODO comments for library shortcut captions
    if todo_marks:
        final_lines = []
        todo_set = {elements[idx]['start'] for idx in todo_marks}
        for i, line in enumerate(new_lines):
            # Map back: we need to find the original line index
            # Since we may have removed lines, use content matching instead
            if is_caption_line(line) and caption_mentions_shortcut(line):
                # Check if already has a TODO comment above
                if not (final_lines and '<!-- TODO:' in final_lines[-1]):
                    final_lines.append('<!-- TODO: insert library shortcut code block for this caption -->')
            final_lines.append(line)
        new_lines = final_lines

    # Add FIXME comments for uncertain captions
    if fixme_marks:
        # Collect the original line content of captions to mark (first line of each)
        fixme_first_lines = set()
        for idx in fixme_marks:
            first_line = elements[idx]['lines'][0].strip()
            fixme_first_lines.add(first_line)

        final_lines = []
        for i, line in enumerate(new_lines):
            if is_caption_line(line) and line.strip() in fixme_first_lines:
                # Check not already marked
                if not (final_lines and '<!-- FIXME:' in final_lines[-1]):
                    final_lines.append('<!-- FIXME: stacked caption, needs manual review -->')
                fixme_first_lines.discard(line.strip())  # only mark once
            final_lines.append(line)
        new_lines = final_lines

    content = '\n'.join(new_lines)

    # Clean up: remove excessive blank lines (3+ consecutive -> 2)
    content = re.sub(r'\n{4,}', '\n\n\n', content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        return True, report
    return False, report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    root = Path(__file__).resolve().parent.parent.parent

    total_files_changed = 0
    total_actions = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip archive directories
        if '_archive' in dirpath or 'node_modules' in dirpath:
            continue

        for fname in sorted(filenames):
            if not fname.startswith('section-') or not fname.endswith('.html'):
                continue

            filepath = os.path.join(dirpath, fname)
            changed, report = fix_file(filepath)

            if changed:
                total_files_changed += 1
                relpath = os.path.relpath(filepath, root)
                print(f"FIXED: {relpath}")
                for line in report:
                    print(line)
                total_actions += len(report)

    print(f"\n=== Summary ===")
    print(f"Files modified: {total_files_changed}")
    print(f"Actions taken: {total_actions}")

    return 0


if __name__ == '__main__':
    sys.exit(main())

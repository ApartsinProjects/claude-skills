#!/usr/bin/env python3
"""Audit section HTML files for misplaced illustrations.

Detects:
1. Preamble illustrations that likely belong in a later section
2. Illustrations placed under the wrong h2 section
3. Orphan figures with no in-text reference

Uses only the Python standard library.
"""

import io
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

class StructureParser(HTMLParser):
    """Extract h2 headings, figures, diagram-containers, and body text."""

    def __init__(self):
        super().__init__()
        self._tag_stack = []
        self._capture = None          # current capture target key
        self._buf = []

        # Results
        self.h2s = []                  # list of (offset, heading_text)
        self.figures = []              # list of dict with keys: offset, caption, alt, fig_id, kind
        self.body_text = ""            # full text content for reference scanning
        self._body_parts = []

        # Tracking
        self._offset = 0              # character offset in source
        self._in_figure = False
        self._in_diagram = False
        self._fig_info = {}

    # -- helpers --
    def _attrs_dict(self, attrs):
        return dict(attrs)

    def handle_starttag(self, tag, attrs):
        ad = self._attrs_dict(attrs)
        self._tag_stack.append(tag)
        pos = self.getpos()  # (line, col)
        offset = pos[0]      # use line number as offset proxy

        # h2
        if tag == "h2":
            self._capture = "h2"
            self._buf = []

        # figure.illustration
        if tag == "figure" and "illustration" in ad.get("class", ""):
            self._in_figure = True
            self._fig_info = {"offset": offset, "kind": "figure.illustration", "caption": "", "alt": "", "fig_id": ""}

        # div.diagram-container
        if tag == "div" and "diagram-container" in ad.get("class", ""):
            self._in_diagram = True
            self._fig_info = {"offset": offset, "kind": "div.diagram-container", "caption": "", "alt": "", "fig_id": ""}

        # img alt text inside figure
        if tag == "img" and (self._in_figure or self._in_diagram):
            self._fig_info["alt"] = ad.get("alt", "")

        # figcaption or diagram-caption
        if tag == "figcaption" or (tag == "div" and "diagram-caption" in ad.get("class", "")):
            if self._in_figure or self._in_diagram:
                self._capture = "caption"
                self._buf = []

    def handle_endtag(self, tag):
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        if tag == "h2" and self._capture == "h2":
            text = " ".join("".join(self._buf).split())
            self.h2s.append((self.getpos()[0], text))
            self._capture = None
            self._buf = []

        if self._capture == "caption" and tag in ("figcaption", "div"):
            caption_text = " ".join("".join(self._buf).split())
            self._fig_info["caption"] = caption_text
            # Extract figure ID like "Figure 20.1.3"
            m = re.search(r"Figure\s+[\d]+\.[\d]+\.[\d]+", caption_text)
            if m:
                self._fig_info["fig_id"] = m.group(0)
            self._capture = None
            self._buf = []

        if tag == "figure" and self._in_figure:
            self._in_figure = False
            self.figures.append(dict(self._fig_info))
            self._fig_info = {}

        if tag == "div" and self._in_diagram:
            # diagram-container may have nested divs, only close at the right level
            # Heuristic: if we have a caption captured, we are done
            if self._fig_info.get("caption") or self._fig_info.get("alt"):
                self._in_diagram = False
                self.figures.append(dict(self._fig_info))
                self._fig_info = {}

    def handle_data(self, data):
        if self._capture in ("h2", "caption"):
            self._buf.append(data)
        self._body_parts.append(data)

    def close(self):
        super().close()
        # Flush any in-progress diagram that never closed cleanly
        if self._in_diagram and self._fig_info:
            self.figures.append(dict(self._fig_info))
            self._in_diagram = False
        self.body_text = " ".join("".join(self._body_parts).split())


def parse_file(filepath):
    parser = StructureParser()
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    parser.feed(content)
    parser.close()
    return parser, content


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def significant_words(text, min_len=4):
    """Extract significant words from text (lowercased, length >= min_len)."""
    stop = {
        "this", "that", "with", "from", "into", "about", "which", "their",
        "they", "them", "than", "when", "what", "each", "more", "most",
        "also", "have", "been", "will", "would", "could", "should",
        "does", "doing", "being", "were", "while", "where", "here",
        "there", "then", "both", "other", "some", "such", "only",
        "over", "very", "just", "like", "between", "through", "after",
        "before", "these", "those", "show", "shows", "figure", "strong",
        "across", "using", "every", "under", "above", "below",
        "different", "same", "many", "much", "well", "still",
        "even", "without", "within", "along", "during", "however",
    }
    words = set()
    for w in re.findall(r"[a-z][a-z'-]+", text.lower()):
        if len(w) >= min_len and w not in stop:
            words.add(w)
    return words


def heading_clean(h2_text):
    """Remove numbering and badges from h2 text for keyword extraction."""
    # Strip leading numbers like "1. " or "2.3 "
    t = re.sub(r"^\d+[\.\d]*\.?\s*", "", h2_text)
    # Strip badge text like "Basic", "Intermediate", "Advanced"
    t = re.sub(r"\b(Basic|Intermediate|Advanced)\b", "", t, flags=re.I)
    return t.strip()


def find_section_for_figure(fig, h2s):
    """Return which h2 section a figure is under (based on line offset)."""
    current_section = "(preamble)"
    for h2_offset, h2_text in h2s:
        if h2_offset <= fig["offset"]:
            current_section = h2_text
        else:
            break
    return current_section


def keyword_overlap(fig_words, heading_words):
    """Score how well figure keywords match a heading."""
    if not heading_words:
        return 0
    return len(fig_words & heading_words)


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def audit_file(filepath, relpath):
    findings = []
    parser, raw_content = parse_file(filepath)
    h2s = parser.h2s
    figures = parser.figures

    if not figures:
        return findings

    # Build h2 keyword map
    h2_keywords = []
    for offset, text in h2s:
        clean = heading_clean(text)
        kw = significant_words(clean)
        h2_keywords.append((offset, text, kw))

    # For each h2, also collect body text under it (between this h2 and next)
    # to find section-specific terms
    h2_body_keywords = {}
    lines = raw_content.split("\n")
    for i, (offset, text, _) in enumerate(h2_keywords):
        start_line = offset
        end_line = h2_keywords[i + 1][0] if i + 1 < len(h2_keywords) else len(lines) + 1
        section_text = " ".join(lines[start_line - 1 : end_line - 1])
        section_words = significant_words(section_text)
        h2_body_keywords[text] = section_words

    first_h2_offset = h2s[0][0] if h2s else 999999

    for fig in figures:
        caption = fig["caption"]
        alt = fig["alt"]
        fig_id = fig["fig_id"]
        fig_text = f"{caption} {alt}"
        fig_words = significant_words(fig_text)
        current_section = find_section_for_figure(fig, h2s)
        short_caption = caption[:100] if caption else alt[:100]

        # ----- Check 1: Preamble illustration -----
        if fig["offset"] < first_h2_offset and h2_keywords:
            best_match = None
            best_score = 0
            for h2_off, h2_text, h2_kw in h2_keywords:
                # Check against heading keywords AND body keywords
                heading_score = keyword_overlap(fig_words, h2_kw)
                body_kw = h2_body_keywords.get(h2_text, set())
                # Only count body terms that are fairly unique to that section
                body_score = keyword_overlap(fig_words, body_kw)
                # Weight heading matches more heavily
                score = heading_score * 3 + body_score * 0.1
                if score > best_score:
                    best_score = score
                    best_match = h2_text
            if best_match and best_score > 1.5:
                findings.append({
                    "type": "PREAMBLE_FIGURE",
                    "file": relpath,
                    "caption": short_caption,
                    "current": "(preamble)",
                    "suggested": best_match,
                    "score": round(best_score, 1),
                })

        # ----- Check 2: Wrong h2 section -----
        if fig["offset"] >= first_h2_offset and h2_keywords:
            best_match = None
            best_score = 0
            current_score = 0
            for h2_off, h2_text, h2_kw in h2_keywords:
                heading_score = keyword_overlap(fig_words, h2_kw)
                body_kw = h2_body_keywords.get(h2_text, set())
                body_score = keyword_overlap(fig_words, body_kw)
                score = heading_score * 3 + body_score * 0.1
                if h2_text == current_section:
                    current_score = score
                if score > best_score:
                    best_score = score
                    best_match = h2_text
            # Only flag if another section scores notably higher than current
            if best_match and best_match != current_section and best_score > current_score + 2.0:
                findings.append({
                    "type": "WRONG_SECTION",
                    "file": relpath,
                    "caption": short_caption,
                    "current": current_section,
                    "suggested": best_match,
                    "score": round(best_score - current_score, 1),
                })

        # ----- Check 3: Orphan figures -----
        if fig_id:
            # Check if fig_id (e.g., "Figure 20.1.3") is referenced in the body text
            # outside of the figcaption/diagram-caption itself
            pattern = re.escape(fig_id)
            matches = list(re.finditer(pattern, raw_content))
            # The figure label appears at least once in its own caption. If it only
            # appears there (or in a diagram-caption), it may be orphaned.
            ref_count = 0
            for m in matches:
                # Check if this occurrence is inside a figcaption or diagram-caption
                # by looking at surrounding context
                start = max(0, m.start() - 200)
                context_before = raw_content[start : m.start()]
                # If there is a <figcaption or diagram-caption tag opened but not
                # closed before this match, it is the caption itself
                in_caption = False
                for tag_name in ["figcaption", 'class="diagram-caption"']:
                    last_open = context_before.rfind(tag_name)
                    if last_open != -1:
                        # Check no closing tag after it
                        close_tag = "</figcaption" if "figcaption" in tag_name else "</div"
                        last_close = context_before.rfind(close_tag, last_open)
                        if last_close == -1:
                            in_caption = True
                            break
                if not in_caption:
                    ref_count += 1
            if ref_count == 0:
                findings.append({
                    "type": "ORPHAN_FIGURE",
                    "file": relpath,
                    "caption": short_caption,
                    "current": current_section,
                    "suggested": "(no in-text reference found)",
                })

    return findings


def main():
    # Collect all section HTML files, excluding _archive
    section_files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # Skip archive directories
        dirnames[:] = [d for d in dirnames if d != "_archive"]
        for fn in filenames:
            if fn.startswith("section-") and fn.endswith(".html"):
                full = os.path.join(dirpath, fn)
                section_files.append(full)

    section_files.sort()
    print(f"Scanning {len(section_files)} section files for misplaced illustrations...\n")

    all_findings = []
    for filepath in section_files:
        relpath = os.path.relpath(filepath, ROOT).replace("\\", "/")
        try:
            findings = audit_file(filepath, relpath)
            all_findings.extend(findings)
        except Exception as e:
            print(f"  ERROR parsing {relpath}: {e}", file=sys.stderr)

    # Print results grouped by type
    preamble = [f for f in all_findings if f["type"] == "PREAMBLE_FIGURE"]
    wrong = [f for f in all_findings if f["type"] == "WRONG_SECTION"]
    orphans = [f for f in all_findings if f["type"] == "ORPHAN_FIGURE"]

    print("=" * 90)
    print(f"  PREAMBLE FIGURES THAT MAY BELONG IN A LATER SECTION: {len(preamble)}")
    print("=" * 90)
    for f in preamble:
        print(f"\n  File:      {f['file']}")
        print(f"  Caption:   {f['caption']}")
        print(f"  Current:   {f['current']}")
        print(f"  Suggested: {f['suggested']}")
        print(f"  Score:     {f['score']}")

    print()
    print("=" * 90)
    print(f"  ILLUSTRATIONS POSSIBLY UNDER WRONG H2 SECTION: {len(wrong)}")
    print("=" * 90)
    for f in wrong:
        print(f"\n  File:      {f['file']}")
        print(f"  Caption:   {f['caption']}")
        print(f"  Current:   {f['current']}")
        print(f"  Suggested: {f['suggested']}")
        print(f"  Delta:     +{f['score']}")

    print()
    print("=" * 90)
    print(f"  ORPHAN FIGURES (no in-text reference): {len(orphans)}")
    print("=" * 90)
    for f in orphans:
        print(f"\n  File:      {f['file']}")
        print(f"  Caption:   {f['caption']}")
        print(f"  Section:   {f['current']}")

    print()
    print("-" * 90)
    total = len(all_findings)
    print(f"TOTAL FINDINGS: {total}  (preamble={len(preamble)}, wrong_section={len(wrong)}, orphan={len(orphans)})")
    print("-" * 90)


if __name__ == "__main__":
    main()

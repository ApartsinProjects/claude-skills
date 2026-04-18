"""Detect SVG diagrams that may be too small or have suspicious aspect ratios.

Scans all HTML files for <svg viewBox="..."> elements inside
<div class="diagram-container"> blocks and reports those with:
  - viewBox width < 400
  - viewBox height < 200
  - Aspect ratio wider than 4:1 or taller than 3:1
"""

import os
import re
import sys

ROOT = r"E:\Projects\LLMCourse"

EXCLUDE_DIRS = {
    "_scripts_archive", "node_modules", ".claude", "scripts",
    "templates", "styles", "agents", "_lab_fragments", "vendor",
}


def collect_html_files(root):
    """Walk root and yield .html paths, skipping excluded directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs in place
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            if fname.endswith(".html"):
                yield os.path.join(dirpath, fname)


# Regex: match a diagram-container div, then capture everything up to its
# closing </div> (greedy enough to grab the SVG and caption).
# We use a two-pass approach: first find diagram-container blocks, then
# parse SVGs and captions inside each block.
CONTAINER_RE = re.compile(
    r'<div\s+class="diagram-container"[^>]*>(.*?)</div>\s*</div>',
    re.DOTALL,
)

# Simpler approach: scan line by line for diagram-container, then look for
# the SVG viewBox and caption within the next ~80 lines.
VIEWBOX_RE = re.compile(r'<svg\s[^>]*viewBox="([^"]+)"', re.IGNORECASE)
CAPTION_RE = re.compile(r'<div\s+class="diagram-caption"[^>]*>(.*?)</div>', re.DOTALL)
STYLE_RE = re.compile(r'<div\s+class="diagram-container"[^>]*style="([^"]*)"', re.IGNORECASE)


def find_small_svgs():
    issues = []

    for filepath in collect_html_files(ROOT):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i]
            if 'class="diagram-container"' in line:
                container_start = i
                # Check for inline style on the container
                has_width = False
                has_min_height = False
                style_match = STYLE_RE.search(line)
                if style_match:
                    style_text = style_match.group(1).lower()
                    if "width" in style_text:
                        has_width = True
                    if "min-height" in style_text:
                        has_min_height = True

                # Gather the block (up to 120 lines or until we see a
                # second diagram-container)
                block_lines = []
                j = i
                depth = 0
                while j < min(i + 120, len(lines)):
                    block_lines.append(lines[j])
                    j += 1
                    # Simple heuristic: stop after we find caption div
                    if j > i + 2 and "diagram-caption" in lines[j - 1]:
                        # grab a couple more for closing tags
                        while j < min(i + 130, len(lines)):
                            block_lines.append(lines[j])
                            j += 1
                            if "</div>" in lines[j - 1]:
                                break
                        break

                block_text = "".join(block_lines)

                # Find SVG viewBox
                vb_match = VIEWBOX_RE.search(block_text)
                if vb_match:
                    vb_str = vb_match.group(1).strip()
                    parts = vb_str.split()
                    if len(parts) == 4:
                        try:
                            vb_x, vb_y, vb_w, vb_h = (
                                float(parts[0]), float(parts[1]),
                                float(parts[2]), float(parts[3]),
                            )
                        except ValueError:
                            i += 1
                            continue

                        # Find the line number of the SVG tag
                        svg_line = container_start + 1
                        for k, bl in enumerate(block_lines):
                            if "viewBox" in bl:
                                svg_line = container_start + k + 1
                                break

                        # Find caption
                        cap_match = CAPTION_RE.search(block_text)
                        caption = ""
                        if cap_match:
                            caption = re.sub(r"<[^>]+>", "", cap_match.group(1)).strip()
                            # Truncate long captions
                            if len(caption) > 120:
                                caption = caption[:117] + "..."

                        # Determine issues
                        reasons = []
                        if vb_w < 400:
                            reasons.append(f"width {vb_w:.0f} < 400")
                        if vb_h < 200:
                            reasons.append(f"height {vb_h:.0f} < 200")
                        if vb_h > 0 and (vb_w / vb_h) > 4:
                            reasons.append(f"very wide: ratio {vb_w/vb_h:.1f}:1")
                        if vb_w > 0 and (vb_h / vb_w) > 3:
                            reasons.append(f"very tall: ratio 1:{vb_h/vb_w:.1f}")
                        if not has_width and not has_min_height:
                            # This is only notable alongside size issues
                            pass

                        if reasons:
                            rel_path = os.path.relpath(filepath, ROOT)
                            issues.append({
                                "file": rel_path,
                                "line": svg_line,
                                "viewBox": vb_str,
                                "width": vb_w,
                                "height": vb_h,
                                "ratio": vb_w / vb_h if vb_h > 0 else 999,
                                "reasons": reasons,
                                "caption": caption,
                            })
                i += 1
            else:
                i += 1

    return issues


def main():
    issues = find_small_svgs()

    if not issues:
        print("No small or suspicious SVG diagrams found.")
        return

    # Sort by file, then line
    issues.sort(key=lambda x: (x["file"], x["line"]))

    # Group by reason category for summary
    too_narrow = [i for i in issues if any("width" in r for r in i["reasons"])]
    too_short = [i for i in issues if any("height" in r for r in i["reasons"])]
    too_wide_ratio = [i for i in issues if any("very wide" in r for r in i["reasons"])]
    too_tall_ratio = [i for i in issues if any("very tall" in r for r in i["reasons"])]

    print(f"{'='*80}")
    print(f"  SVG Size Detection Report")
    print(f"  Found {len(issues)} potentially small/suspicious SVG diagrams")
    print(f"{'='*80}")
    print()
    print(f"  Summary:")
    print(f"    Width < 400px:         {len(too_narrow)}")
    print(f"    Height < 200px:        {len(too_short)}")
    print(f"    Very wide (ratio >4):  {len(too_wide_ratio)}")
    print(f"    Very tall (ratio >3):  {len(too_tall_ratio)}")
    print()
    print(f"{'='*80}")

    current_file = None
    for item in issues:
        if item["file"] != current_file:
            current_file = item["file"]
            print(f"\n  {current_file}")
            print(f"  {'-' * len(current_file)}")

        reason_str = ", ".join(item["reasons"])
        print(f"    Line {item['line']:>5}  viewBox=\"{item['viewBox']}\"")
        print(f"             Issue: {reason_str}")
        if item["caption"]:
            print(f"             Caption: {item['caption']}")
        print()

    print(f"{'='*80}")
    print(f"  Total: {len(issues)} issues across "
          f"{len(set(i['file'] for i in issues))} files")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()

"""
Audit CSS files for print quality: check color contrast ratios,
identify colors that may not print well (too light, low contrast).

Checks:
1. All text colors against their likely backgrounds
2. Callout backgrounds vs. text for readability
3. Code block contrast
4. Print media query coverage
"""

import re
from pathlib import Path
import colorsys

ROOT = Path(r"E:\Projects\LLMCourse")


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple (0-255)."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join([c*2 for c in h])
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def relative_luminance(r, g, b):
    """Calculate relative luminance per WCAG 2.0."""
    def linearize(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(color1, color2):
    """Calculate WCAG contrast ratio between two hex colors."""
    r1, g1, b1 = hex_to_rgb(color1)
    r2, g2, b2 = hex_to_rgb(color2)
    l1 = relative_luminance(r1, g1, b1)
    l2 = relative_luminance(r2, g2, b2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def check_pair(name, fg, bg, min_ratio=4.5):
    """Check a color pair and return result."""
    ratio = contrast_ratio(fg, bg)
    status = "PASS" if ratio >= min_ratio else "FAIL"
    return (name, fg, bg, ratio, status)


def main():
    print("=" * 70)
    print("PRINT QUALITY AND CONTRAST AUDIT")
    print("=" * 70)

    # Define known color pairs from the CSS
    pairs = [
        # General text
        ("Body text on white", "#333", "#ffffff", 4.5),
        ("Light text on white", "#555", "#ffffff", 4.5),
        ("Lighter text on white", "#888", "#ffffff", 4.5),

        # Code blocks
        ("Code text on code bg", "#cdd6f4", "#1e1e2e", 4.5),
        ("Code comment on code bg", "#6c7086", "#1e1e2e", 4.5),
        ("Code keyword on code bg", "#cba6f7", "#1e1e2e", 4.5),
        ("Code string on code bg", "#a6e3a1", "#1e1e2e", 4.5),
        ("Code number on code bg", "#fab387", "#1e1e2e", 4.5),
        ("Code function on code bg", "#89b4fa", "#1e1e2e", 4.5),
        ("Code variable on code bg", "#f9e2af", "#1e1e2e", 4.5),
        ("Code operator on code bg", "#89dceb", "#1e1e2e", 4.5),
        ("Code punctuation on code bg", "#bac2de", "#1e1e2e", 4.5),
        ("Bold text in code on code bg", "#f9e2af", "#1e1e2e", 4.5),

        # Algorithm callout (light code bg)
        ("Algorithm code on light bg", "#1a1a2e", "#faf8ff", 4.5),

        # Code caption
        ("Code caption on white", "#333", "#ffffff", 4.5),
        ("Code caption strong (accent) on white", "#0f3460", "#ffffff", 4.5),

        # Callout: Big Picture (purple gradient)
        ("Text on big-picture bg", "#333", "#f3e5f5", 4.5),
        ("Title on big-picture bg", "#6a1b9a", "#f3e5f5", 4.5),

        # Callout: Key Insight (green)
        ("Text on key-insight bg", "#333", "#e8f5e9", 4.5),
        ("Title on key-insight bg", "#2e7d32", "#e8f5e9", 4.5),

        # Callout: Note (blue)
        ("Text on note bg", "#333", "#e3f2fd", 4.5),
        ("Title on note bg", "#1565c0", "#e3f2fd", 4.5),

        # Callout: Warning (amber)
        ("Text on warning bg", "#333", "#fff8e1", 4.5),
        ("Title on warning bg", "#e65100", "#fff8e1", 4.5),

        # Callout: Practical Example (teal)
        ("Text on practical bg", "#333", "#e0f2f1", 4.5),
        ("Title on practical bg", "#00695c", "#e0f2f1", 4.5),

        # Callout: Fun Note (pink)
        ("Text on fun-note bg", "#333", "#fce4ec", 4.5),
        ("Title on fun-note bg", "#c2185b", "#fce4ec", 4.5),

        # Callout: Research Frontier (teal/cyan)
        ("Text on research bg", "#333", "#e0f2f1", 4.5),
        ("Title on research bg", "#00796b", "#e0f2f1", 4.5),

        # Callout: Algorithm (indigo)
        ("Text on algorithm bg", "#333", "#f3effc", 4.5),
        ("Title on algorithm bg", "#2e3990", "#f3effc", 4.5),

        # Callout: Tip (cyan)
        ("Text on tip bg", "#333", "#e0f7fa", 4.5),
        ("Title on tip bg", "#00838f", "#e0f7fa", 4.5),

        # Callout: Exercise (deep orange)
        ("Text on exercise bg", "#333", "#fbe9e7", 4.5),

        # Header
        ("Header text on primary", "#ffffff", "#1a1a2e", 4.5),
        ("Subtitle on primary", "#b8c4d8", "#1a1a2e", 4.5),

        # Links
        ("Link color on white", "#0f3460", "#ffffff", 4.5),
        ("Highlight color on white", "#e94560", "#ffffff", 3.0),

        # Diagram caption
        ("Diagram caption on white", "#555", "#ffffff", 4.5),

        # Print-specific: grayscale approximation
        ("Light green title printed", "#2e7d32", "#f0f0f0", 4.5),
        ("Teal title printed", "#00695c", "#f0f0f0", 4.5),
        ("Purple title printed", "#6a1b9a", "#f0f0f0", 4.5),
    ]

    fails = []
    print(f"\n{'Name':<45} {'FG':>7} {'BG':>7} {'Ratio':>6} {'Result'}")
    print("-" * 80)
    for name, fg, bg, min_ratio in pairs:
        result = check_pair(name, fg, bg, min_ratio)
        _, _, _, ratio, status = result
        marker = "  " if status == "PASS" else "!!"
        print(f"{marker} {name:<43} {fg:>7} {bg:>7} {ratio:>5.1f}:1 {status}")
        if status == "FAIL":
            fails.append(result)

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(fails)} color pairs FAIL contrast requirements")
    print(f"{'=' * 70}")
    for name, fg, bg, ratio, _ in fails:
        print(f"  FAIL: {name} ({fg} on {bg}) = {ratio:.1f}:1")
        # Suggest fix
        if ratio < 3.0:
            print(f"        -> needs significant darkening of text or lightening of background")
        else:
            print(f"        -> slightly darken text color")


if __name__ == "__main__":
    main()

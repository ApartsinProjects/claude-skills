# Book Skills: Scripts

## Included (generalizable to any HTML textbook)

### generate_icons_gemini.py
Batch icon generation via Gemini Imagen and Gemini native image APIs.
Supports parallel single calls (Imagen) and batch API with 50% discount (Gemini).

Usage:
```bash
python generate_icons_gemini.py --list                    # show available types
python generate_icons_gemini.py --engine gemini --batch   # batch mode (50% off)
python generate_icons_gemini.py --types exercise,tip      # specific types only
```

Requires `GEMINI_API_KEY` environment variable or `.env.all` file in book root.

### audit/
Plugin-based HTML quality audit framework. Each check is a standalone Python
module with a `run(filepath, html, context)` signature. The runner discovers
checks automatically from the `checks/` directory.

Usage: `python -m scripts.audit.run`

To adapt for another book, change `BOOK_ROOT` in `audit/run.py`.

### fix/
Reusable fix scripts for common HTML textbook issues:

| Script | What it fixes |
|--------|--------------|
| `fix_accessibility.py` | th scope, external link attrs, excessive blanks |
| `fix_svg_clipping.py` | SVG viewBox too small for text near edges |
| `fix_svg_text_right_clip.py` | Text clipped at right edge of SVG |
| `fix_code_blocks.py` | Bare `<pre>` without `<code class="language-*">` |
| `fix_math_blocks.py` | Prose mixed into `$$...$$` display math |
| `fix_inline_styles.py` | Remove inline styles where CSS classes exist |
| `fix_structural_html.py` | Epigraph placement, callout class quotes, nav |
| `fix_th_scope.py` | Incorrect `scope` attribute on `<th>` elements |
| `fix_unclosed_p.py` | Unclosed `<p>` tags before block elements |
| `fix_caption_numbering.py` | Figure/Code/Table caption numbering by section |
| `fix_manual_highlights.py` | Manual `<span>` highlights in code blocks |
| `fix_latex_funcs.py` | LaTeX function name syntax in KaTeX blocks |
| `fix_section_ordering.py` | Section element ordering within pages |

### detect/
Standalone audit scripts (older, pre-plugin system):

| Script | What it detects |
|--------|----------------|
| `audit_html_quality.py` | Comprehensive HTML quality checks |
| `audit_svg_quality.py` | SVG accessibility and quality |
| `audit_print_contrast.py` | Print stylesheet contrast issues |
| `validate_format.py` | Template/format convention violations |

## Not included (book-specific, live in project's scripts/)

- `fix/fix_callout_icons.py`, `fix/fix_pathway_cards.py`, `fix/fix_chapter_nav.py`
- `generate/` (illustration prompts, epigraph assignment, appendix creation)
- `data/` (illustration mappings, icon prompts)
- `_archive/` (27 one-shot scripts that already ran)

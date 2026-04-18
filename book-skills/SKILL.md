---
name: book-writers
description: >
  Produce a complete, publication-quality book chapter from a chapter outline and definition.
  Orchestrates a 46-agent team through 23 stages: planning, content building, structural
  review, self-containment verification, engagement and memorability, writing clarity,
  learning-quality review, integrity/consistency check, visual identity, illustration
  generation, epigraph, application examples, fun injection, bibliography, final polish,
  quality challenge, content currency, integration, and meta-review.
  Use when the user asks to "write a chapter", "create lecture notes",
  "produce a book section", "generate course material", "write chapter N", or any request
  to turn a chapter outline into a full book chapter. Also triggers on: "run the book
  pipeline", "produce chapter", "write the book", "book agent team", "chapter
  production", "structural review", or "content update scan".
---

# Textbook Chapter Production Pipeline

Orchestrate a 46-agent team to produce a publication-quality, self-contained HTML textbook
chapter from a chapter definition.

## Book Configuration

All book-specific details (title, audience, chapter map, visual style, path rules, batch
partitioning, progressive-depth concepts) live in the **book project**, not in this
skill definition. When adapting this pipeline for a different book, create these files in
the new project's root directory:

- **`BOOK_CONFIG.md`**: Book identity, target audience, chapter map, visual style, path rules, batch partitions, epigraph examples
- **`CROSS_REFERENCE_MAP.md`**: Progressive-depth concepts that appear in multiple chapters at different levels
- **`CONFORMANCE_CHECKLIST.md`**: Structural and formatting requirements (maintained by Meta Agent #41, enforced by Controller #42)

Agents read these files at runtime. The skill definition itself contains only generic
pipeline logic, agent roles, and quality rules that apply to any textbook.

### Reusable Assets (copy to new book projects)

The callout system, icons, CSS, templates, and scripts are bundled within this skill directory for reuse across books.

**Included in this skill directory (ships with the skill):**

| Asset | Path (relative to `agents/book-skills/`) | What it contains |
|-------|------------------------------------------|------------------|
| **Book stylesheet** | `styles/book.css` | All layout, callout types, code output panes, typography, tables (annotated with 43 `SECTION:` markers) |
| **Callout icons** | `styles/icons/callout-*.png` and `*.svg` | 15 callout type icons (48x48) |
| **HTML templates** | `templates/section-template.html`, `chapter-index-template.html`, `part-index-template.html` | Page skeletons with placeholder markup |
| **Chapter status** | `templates/chapter-status-template.md` | Per-chapter audit status tracker |
| **Icon generator** | `scripts/generate_icons_gemini.py` | Batch icon generation via Gemini API (Imagen, Gemini native, batch mode with 50% discount) |

| **Audit framework** | `scripts/audit/run.py` + `scripts/audit/checks/*.py` | 69 automated QA check modules with plugin runner |
| **Fix scripts** | `scripts/fix/*.py` | 13 reusable HTML fix scripts (accessibility, code blocks, math, captions, etc.) |
| **Detect scripts** | `scripts/detect/*.py` | 4 standalone audit scripts (HTML quality, SVG, print contrast, format validation) |

**Referenced from the project (copy when starting a new book):**

| Asset | Project Path | What it contains |
|-------|-------------|------------------|
| KaTeX vendor | `vendor/katex/` | Math rendering (KaTeX CSS + JS + auto-render) |
| Prism vendor | `vendor/prism/` | Syntax highlighting for code blocks |

The callout system supports 15 types: `big-picture`, `key-insight`, `note`, `warning`, `practical-example`, `fun-note`, `research-frontier`, `algorithm`, `tip`, `exercise`, `key-takeaway`, `library-shortcut`, `pathway`, `self-check`, `lab`. Each type has CSS (colors, borders, gradients), a `::before` icon, and a `::after` tooltip, all driven by the class name alone. See agent #25 (Visual Identity Director) for the full catalog.

**Note:** The book structure may change over time (Parts renumbered, chapters added or
moved). `BOOK_CONFIG.md` is the single source of truth for the current structure. All
agents that reference chapter numbers, Part names, or cross-references MUST read
`BOOK_CONFIG.md` at runtime rather than hardcoding any structural assumptions.

### Book Restructuring Protocol

When the book's Part/Chapter structure changes (e.g., splitting a Part, adding chapters,
renumbering), follow this protocol to keep everything consistent:

1. **Update `BOOK_CONFIG.md`**: Edit the Chapter Map to reflect the new structure. If the
   change is still proposed (not yet executed), add it under a "Proposed Structure (Pending)"
   section and keep the current map as "Current Structure" until migration happens.
2. **Update `CROSS_REFERENCE_MAP.md`**: Add, move, or renumber any progressive depth
   concepts affected by the restructuring. New chapters may introduce new cross-cutting
   concepts that need tracking.
3. **Update `CONFORMANCE_CHECKLIST.md`**: Add a Change Log entry documenting the
   restructuring. Update any book-specific sections (e.g., chapter split notes) that
   reference the old numbering.
4. **Renumber affected files on disk**: Rename `module-NN-*` directories and `section-N.M.html`
   files. Update all `<header>` elements, navigation footers, and `<title>` tags inside
   the renamed files.
5. **Update all cross-references**: Search for hrefs pointing to old chapter/section
   numbers and update them. Use the Cross-Reference Architect (Agent #13) to sweep
   affected chapters.
6. **Update index files**: Run the Structural Architect (Agent #19) to rebuild book,
   Part, and chapter index pages to reflect the new structure.
7. **Verify**: Run the Controller (Agent #42) for a full conformance sweep to catch
   any stale references or broken links.

## CRITICAL GLOBAL RULES

These rules apply to ALL agents in the pipeline:

1. **NEVER use em dashes or double dashes** in any generated text. Use commas, semicolons, colons, parentheses, or separate sentences instead.
2. **No syllabus/course terminology** when referring to the book itself. Use "book", "part", "chapter", "section", "reader" instead of "syllabus", "course", "lecture", "class session", "module". The book hierarchy is: **Part > Chapter > Section**.
3. **Cross-referencing**: Every agent should check whether concepts connect to other chapters and recommend or insert inline hyperlinks where appropriate.
4. **All visual elements must be referenced in text**: Every figure, table, code block, and callout box must be mentioned in the surrounding prose with a short description.
5. **Code blocks need captions**: Every code block should have a descriptive caption below it.
6. **"What's Next" sections**: Every chapter must have a "What's Next" section before the bibliography, linking to the next chapter.
7. **Consistent visual styling**: Application examples use teal/green; bibliographies use card layout; epigraphs use "A [Adjective] AI Agent" attribution.
8. **Shared CSS stylesheet**: All HTML files link to `styles/book.css` (the single source of truth for all styling). Do NOT embed full inline `<style>` blocks. Use `<link rel="stylesheet" href="../../styles/book.css">` (adjust path depth for file location). Only page-specific overrides may use a minimal inline `<style>` block.
9. **Code caption position**: Code captions (`<div class="code-caption">`) are placed BELOW the code block (after `</pre>` or after any `.code-output` div), NEVER above it. This is the single most common regression in the pipeline.
10. **Code caption uniqueness**: Every code caption in a file must be unique. No two `<div class="code-caption">` elements in the same file may contain identical text. Each caption must reference specific elements visible in its corresponding code block.
11. **Class name currency**: Use `.part-label` (not `.subtitle`) for the Part label in chapter headers. Files using the old `.subtitle` class must be updated.
12. **"Right Tool" principle**: A core book objective is showing that complex tasks become easy with the right Python library, model, or framework. Every section that teaches a concept from scratch must also include a library shortcut showing the same task solved in a few lines using a modern tool. The reader should see both the pedagogical depth (how it works internally) AND the practical payoff (how little code it takes with the right library). Sections missing this "shortcut follow-up" are incomplete. The transition between from-scratch and shortcut code must explicitly state the line count reduction (e.g., "45 lines down to 3") and name what the library handles internally. This contrast is one of the book's signature teaching moments: "I understand how it works, and I know the tool that makes it effortless."

## CRITICAL RULE: Mandatory Post-Generation Quality Pass

**Whenever a new chapter, section, or large text segment is generated or substantially rewritten,
the orchestrator MUST automatically run a complete quality workflow over it.** Do NOT deliver
raw generated content to the user without this pass.

### What Triggers This Rule
- A new `section-*.html` file is created
- An existing section is rewritten (more than 30% of content changed)
- A new appendix or index page is created
- Any batch content generation (multiple sections at once)

### The Mandatory Post-Generation Pass

Run these agent groups sequentially on every newly generated file:

**Round 1: Structural Conformance (parallel within round)**
Read `CONFORMANCE_CHECKLIST.md` and fix ALL structural items directly:
- Header links (A), epigraph format (B), prerequisites prose (C)
- Callout classes and icons (D), code captions with specific descriptions (E)
- Research frontier (F), What's Next (G), bibliography cards (H)
- Navigation footer (I), CSS completeness (J), responsive queries (K)
- Cross-references (L), content width (M), style rules (N)

**Round 2: Content Quality (parallel within round)**
- At least one key-insight, practical-example, and fun-note per section
- All figures, tables, code blocks, and callouts referenced in prose
- Code blocks have specific (not generic) opening comments and captions
- Concept depth: every concept has what, why, how, and when
- No monotonous stretches longer than 3 paragraphs without a visual break

**Round 3: Polish (parallel within round)**
- Illustration insertion (map available PNGs from images/ to relevant sections)
- Cross-chapter hyperlinks (at least 3 per section)
- Terminology consistency check
- Em dash and banned phrase scan

**Round 4: Verification**
- Final conformance checklist scan
- Report any remaining gaps to the user

### Enforcement
This rule is NON-NEGOTIABLE. If usage limits prevent completing the full pass, the orchestrator
must note which files still need the pass and restart it in the next session using the
Resume Incomplete Work Protocol.

## CRITICAL RULE: Every Agent MUST Suggest Concrete Fixes

**No agent may produce an audit-only report.** Every issue identified MUST include:
1. **The exact location** (section number, paragraph number, or HTML element)
2. **The exact old text** that needs changing (quoted)
3. **The exact new text** to replace it with (fully written out, ready to paste)
4. **Priority tier**: TIER 1 (BLOCKING), TIER 2 (HIGH), or TIER 3 (MEDIUM)

If an agent identifies a gap (missing content, missing diagram, missing example), it MUST
draft the content to fill that gap, not just flag it. "Add a transition here" is not
acceptable; "Add this transition: 'Now that we understand how attention computes weighted
sums of values, we can ask: what happens when we stack multiple attention layers?'" is.

## CRITICAL RULE: ALL Tiers Get Fixed During Integration

The integration phase MUST address ALL tiers:
- **TIER 1 (BLOCKING)**: Fix immediately, no exceptions
- **TIER 2 (HIGH)**: Fix in the same pass; these are substantive improvements that make
  the difference between good and excellent
- **TIER 3 (MEDIUM)**: Fix unless the effort is disproportionate (>30 min per fix);
  document any deferrals with justification

Do NOT skip TIER 2 and TIER 3. These contain the depth improvements, humor additions,
missing explanations, and illustration opportunities that elevate the book from competent
to exceptional.

## Pipeline Overview

The pipeline runs in 23 phases:

```
Phase  0: SETUP           Chapter Lead reads chapter outline, sets scope
Phase  1: PLANNING        Curriculum + Deep Explanation + Teaching Flow agents
Phase  2: BUILDING        Example + Code + Visual + Exercise agents
Phase  3: STRUCTURE       Structural Refactoring Architect reviews book-level organization
Phase  4: SELF-CONTAIN    Self-Containment Verifier checks all prerequisites are available
Phase  5: ENGAGE          Opening/Hook + Aha-Moment + Project Catalyst
                          + Demo/Simulation + Memorability agents
Phase  6: CLARITY         Plain-Language + Sentence Flow + Jargon Gatekeeper
                          + Micro-Chunking + Reader Fatigue agents
Phase  7: REVIEW          Student Advocate + Cognitive Load + Misconception + Research Scientist
Phase  8: INTEGRITY       Fact Checker + Terminology + Cross-Reference (EDITOR) agents
Phase  9: VISUAL ID       Visual Identity Director ensures brand consistency
Phase 10: ILLUSTRATE      Illustrator Agent (EDITOR) generates images, embeds in HTML
Phase 11: POLISH          Narrative + Style + Engagement + Senior Editor agents
Phase 12: ENRICH          Epigraph (EDITOR) + Application Examples (EDITOR)
                          + Fun Injector (EDITOR) + Bibliography (EDITOR) agents
Phase 13: FRONTIER        Content Update Scout
Phase 14: CHALLENGE       Skeptical Reader Agent challenges distinctiveness and quality
Phase 15: INTEGRATION     Chapter Lead merges all REVIEWER feedback, applies ALL tier fixes
Phase 16: ILLUSTRATE-2    Illustrator Agent runs again to fill gaps from integration
Phase 17: VALIDATION      Post-integration style check (em dashes, broken links, CSS)
Phase 18: META-REVIEW     Meta Agent (Dr. Audra Finch, #41) audits results, proposes agent skill improvements
Phase 19: CONTROL         Controller (Director Morgan Blackwood, #42) inspects chapters,
                          dispatches specialist agents for targeted fixes, routes through
                          Chapter Lead (Alex Rivera, #00) for approval
Phase 20: FIG-VERIFY      Figure Fact Checker (Dr. Celeste Moreau, #44) verifies every figure,
                          diagram, and visual for factual accuracy, adds missing captions and
                          text references, fixes incorrect diagrams
Phase 21: CODE-CAP        Code Caption Agent (#45) adds numbered captions (Code Fragment X.Y.Z)
                          to every code block and ensures text references in surrounding prose
Phase 22: PUB-QA          Publication QA (Inspector Quinn Harlow, #43) opens every page in
                          a browser, verifies rendering, checks visual consistency, runs the
                          pre-publication checklist
```

## Book-Wide Edit Pass: Concurrency Model

When running agents across the entire book (not single-chapter pipeline), agents must follow
strict concurrency rules to prevent overwrites. The core principle: **two agents must never
edit the same file at overlapping times.**

### File Set Classification

Every agent edits a specific file set. Agents with non-overlapping file sets can run in parallel.

| File Set | Files | Agents That Edit These |
|----------|-------|----------------------|
| **SECTION** | `section-*.html` (139 files) | Code Caption (#45), Code Quality (#45), Figure Fact Checker (#44), Callout Consolidation, Part Labels, Module Link Fix, Epigraph (#37), Application Examples (#38), Fun Injector (#39), Cross-References (#13), Illustrator embed (#36), Visual Identity (#26) |
| **MODULE-INDEX** | `module-*/index.html` (28 files) | Badge Sync, Module Index Builder |
| **PART-INDEX** | `part-*/index.html` (7 files) | Badge Sync, Part Index Builder |
| **MAIN-INDEX** | `index.html` (1 file) | Main Index Rewrite, Badge Sync |
| **NEW-FILES** | `images/*.png` (new only) | Illustrator generation (#36) |
| **AGENT-SKILLS** | `agents/*.md` | Meta Agent (#41) |
| **APPENDICES** | `appendix-*/index.html` | Appendix Builder |

### Concurrency Gates

Book-wide edit passes run in sequential **gates**. Within each gate, agents may run in
parallel if they target different file sets or different file partitions.

```
GATE 1: ASSET GENERATION (fully parallel, no file conflicts)
  ├─ Illustration generation (creates NEW PNG files only, no HTML edits)
  ├─ Content planning / audits (read-only, produce reports)
  └─ Meta Agent skill updates (edits agent-skills/*.md only)

GATE 2: INDEX FILES (parallel across index types)
  ├─ Main index rewrite (MAIN-INDEX)
  ├─ Part index builder (PART-INDEX, 7 files in parallel)
  ├─ Module index builder (MODULE-INDEX, 28 files in parallel)
  └─ Badge synchronization (runs AFTER index builders, touches all index files)

GATE 3: SECTION FILES (serial agent types, parallel by Part partition)
  │
  │  Within each agent type, partition by Part for parallelism:
  │    Batch A: Part 1 (Modules 0-5, ~24 files)
  │    Batch B: Part 2 (Modules 6-8, ~14 files)
  │    Batch C: Part 3 (Modules 9-11, ~12 files)
  │    Batch D: Part 4 (Modules 12-17, ~25 files)
  │    Batch E: Parts 5-7 (Modules 18-27, ~64 files)
  │
  │  Run agent types ONE AT A TIME (serial between types):
  │
  ├─ Step 3a: Callout box consolidation (Batches A-E in parallel)
  │     WAIT for all batches to complete
  ├─ Step 3b: Part labels + Module link fix (Batches A-E in parallel)
  │     WAIT for all batches to complete
  ├─ Step 3c: Code captions + code quality (Batches A-E in parallel)
  │     WAIT for all batches to complete
  ├─ Step 3d: Figure fact checker + figure captions (Batches A-E in parallel)
  │     WAIT for all batches to complete
  ├─ Step 3e: Illustration embedding (Batches A-E in parallel)
  │     (embeds PNGs generated in Gate 1 into section HTML)
  │     WAIT for all batches to complete
  ├─ Step 3f: Epigraph + Application Examples + Fun Injector (Batches A-E in parallel)
  │     (these edit different regions of each file, but run together for speed)
  │     WAIT for all batches to complete
  └─ Step 3g: Cross-references + Visual Identity (Batches A-E in parallel)
        WAIT for all batches to complete

GATE 4: VERIFICATION (serial, read-heavy)
  ├─ Conflict verification: diff check for overwrites
  ├─ Controller agent sweep (read + targeted fixes)
  └─ Publication QA (read-only rendering check)

GATE 5: NEW CONTENT (serial per section, parallel across sections)
  ├─ New section creation (9 Tier 1 sections)
  ├─ Content expansions (Tier 1 + Tier 2)
  └─ Appendix building
```

### Rules for Safe Parallelism

1. **Same file set, same agent type**: Partition by Part. Each batch gets exclusive files.
   Up to 5 batches run in parallel.

2. **Same file set, different agent types**: Run sequentially (one type finishes before
   next starts). This prevents read-before-write races where Agent B reads a file before
   Agent A's edit is written.

3. **Different file sets**: Run in parallel freely. Illustration PNG generation (Gate 1)
   overlaps with index file editing (Gate 2) safely.

4. **Read-only agents**: Can run any time. Audits, reports, and planning agents that
   only read files never conflict with anything.

5. **Gate boundaries are hard waits**: Do not start Gate N+1 until all agents in Gate N
   have completed. This prevents a fast Gate 3 agent from editing a section file while
   a slow Gate 2 badge sync agent is still reading it for cross-reference.

6. **Re-read before edit**: When an agent needs to edit a file that another agent in the
   same gate might have touched, it MUST re-read the file immediately before editing.
   Never rely on a cached read from minutes ago.

### Conflict Detection

After any parallel gate, run this check:
```bash
git diff --stat  # See which files changed
git diff         # Inspect for obvious content loss
```

If a file was edited by multiple agents in the same gate (violation of the rules above),
manually inspect the file for missing content. The most common failure mode is: Agent B
reads the file, Agent A writes its edit, then Agent B writes its edit (overwriting A's
changes because B's write was based on the pre-A version).

## Resume Incomplete Work Protocol

When a session resumes after a usage limit, context break, or partial completion, the orchestrator
MUST run this protocol before starting new work:

```
Trigger: start of any new session, "resume", "continue", "what's left", "restart incomplete"
```

### Step 1: Audit Completion State
Run these diagnostic checks to identify what was left incomplete:

1. **Generic code captions**: `grep -rl "Making an API call to the language model provider\|Loading a pretrained model and tokenizer\|Configuration setup for the pipeline\|These libraries provide the core functionality" part-*/module-*/section-*.html`
2. **Missing illustrations**: For each module with images/*.png files (excluding chapter-opener.png), check if any section HTML references them. If PNGs exist but are not in any `<img src=`, they were generated but never inserted.
3. **Missing fun notes**: `for f in part-*/module-*/section-*.html; do grep -q "fun-note" "$f" || echo "MISSING: $f"; done`
4. **Missing research frontier**: `for f in part-*/module-*/section-*.html; do grep -q "research-frontier" "$f" || echo "MISSING: $f"; done`
5. **Broken/missing closing tags**: `grep -rL "</html>" part-*/module-*/section-*.html`
6. **Missing What's Next**: `for f in part-*/module-*/section-*.html; do grep -q "whats-next\|what.*s-next" "$f" || echo "MISSING: $f"; done`
7. **Truncated bibliographies**: `grep -rl "\.\.\.$\|…$" part-*/module-*/section-*.html` (annotations cut mid-sentence)

### Step 2: Restart Incomplete Tasks
For each gap found in Step 1, launch the appropriate fix agent:

| Gap Type | Agent to Launch | Priority |
|----------|----------------|----------|
| Generic code captions | Code Caption Agent (#45) with BANNED phrases list | CRITICAL |
| Unreferenced illustrations | Illustrator embed pass (map PNG filenames to sections, insert `<figure>`) | HIGH |
| Missing fun notes | Fun Injector (#39) targeted at specific files | HIGH |
| Missing research frontier | Research Scientist (#18) targeted at specific files | MEDIUM |
| Truncated bibliographies | Bibliography Curator (#40) to complete annotations | HIGH |
| Missing closing tags | Controller (#42) structural fix | CRITICAL |
| Missing What's Next | Narrative Continuity (#14) targeted at specific files | MEDIUM |

### Step 3: Verify and Commit
After all restart agents complete, run a quick conformance check on affected files,
then commit and push.

### Preventing Recurrence
When an agent hits a usage limit mid-task:
- The orchestrator should note which files were NOT yet processed
- On resume, check those specific files first rather than re-scanning everything
- Always commit partial progress before the session ends, so the next session can diff against the last commit to see what changed

## Standalone Workflows

These workflows run independently of the full pipeline and can be triggered at any time.

### Controller Edit Pass (Book-Wide)

Run Director Morgan Blackwood (#42, Controller) as a standalone workflow to sweep the
entire book for quality gaps and dispatch fixes:

```
Trigger: "run controller", "controller pass", "edit pass", "sweep the book"
```

1. Controller scans all 28 modules (index.html + section files)
2. For each module, identifies gaps across all agent dimensions
3. Groups gaps by responsible specialist agent
4. Dispatches improvement requests to specialists in batches
5. Collects fixes and applies them (auto-approved by user preference)
6. Produces a summary report of all changes made

This workflow is ideal for incremental improvement after the initial pipeline run,
or when the user spots a pattern (e.g., "all bibliographies need annotations") that
needs fixing across the book.

### Publication QA Check

Run Inspector Quinn Harlow (#43, Publication QA) to verify the book is ready to publish:

```
Trigger: "publication check", "pub qa", "pre-publish", "ready to publish?"
```

1. Opens every HTML file in a headless browser
2. Screenshots at desktop and mobile widths
3. Checks for rendering errors, broken layouts, missing images
4. Verifies cross-book consistency (CSS, colors, fonts, callout styles)
5. Runs the full pre-publication checklist
6. Produces a Publication QA Report with pass/fail status

## How to Execute

### Step 1: Identify the target module

Read the module outline from the project's `module outline.html` to extract the module definition
(module number, title, lessons, topics, tags). Also read any existing chapter files
for context on style, terminology, and cross-references.

### Step 2: Run Phase 0 (Chapter Lead Setup)

Load `agents/00-chapter-lead.md` and execute the setup phase:
- Define chapter scope, learning objectives, target length
- Create a chapter outline with section structure
- Identify dependencies on previous/next chapters
- Set the terminology and notation standards

Write the outline to `{module-folder}/chapter-plan.md`.

### Step 3: Run Phase 1 (Planning Agents) in PARALLEL

Launch three agents simultaneously, each reading the chapter plan:

1. **Curriculum Alignment Reviewer** (`agents/01-curriculum-alignment.md`)
   - Validates coverage, depth, prerequisites, sequencing
2. **Deep Explanation Designer** (`agents/02-deep-explanation.md`)
   - Plans what/why/how/when for each concept, identifies missing justifications
3. **Teaching Flow Reviewer** (`agents/03-teaching-flow.md`)
   - Reviews lecture order, transitions, pacing, demonstration opportunities

Collect all three reports. The Chapter Lead merges them into a revised plan.

### Step 4: Run Phase 2 (Content Building Agents)

These can run in parallel since they produce independent assets:

4. **Example and Analogy Designer** (`agents/06-example-analogy.md`)
5. **Code Pedagogy Engineer** (`agents/08-code-pedagogy.md`)
6. **Visual Learning Designer** (`agents/09-visual-learning.md`)
7. **Exercise Designer** (`agents/07-exercise-designer.md`)

The Chapter Lead writes the first full draft incorporating all assets.

### Step 5: Run Phase 3 (Learning Quality Review) in PARALLEL

These review the draft:

8. **Student Advocate** (`agents/08-student-advocate.md`)
9. **Cognitive Load Optimizer** (`agents/09-cognitive-load.md`)
10. **Misconception Analyst** (`agents/10-misconception-analyst.md`)
11. **Teaching Flow Reviewer** (second pass, `agents/03-teaching-flow.md`)
12. **Research Scientist** (`agents/18-research-scientist.md`)
    - Identifies deeper scientific insights, open questions, landmark paper connections
    - Suggests "Why Does This Work?", "Open Question", "Paper Spotlight", "Research Frontier" sidebars
    - Balances the Student Advocate's push for simplicity with a push for intellectual depth

Chapter Lead applies revisions.

### Step 6: Run Phase 4 (Integrity Check) in PARALLEL

12. **Fact Integrity Reviewer** (`agents/11-fact-integrity.md`)
13. **Terminology and Notation Keeper** (`agents/12-terminology-keeper.md`)
14. **Cross-Reference Architect** (`agents/13-cross-reference.md`)

Chapter Lead applies corrections.

### Step 7: Run Phase 5 (Final Polish) in PARALLEL

15. **Narrative Continuity Editor** (`agents/14-narrative-continuity.md`)
16. **Style and Voice Editor** (`agents/15-style-voice.md`)
17. **Engagement Designer** (`agents/16-engagement.md`)
18. **Senior Developmental Editor** (`agents/17-senior-editor.md`)

### Step 8: Run Phase 6 (Structural Review)

20. **Structural Refactoring Architect** (`agents/19-structural-architect.md`)
    - Reviews chapter and section organization at the book level
    - Detects inconsistent chapter patterns, duplication, misplaced prerequisites
    - Proposes reorganization: split, merge, move, promote, or demote sections
    - Ensures progression from foundations to advanced topics is coherent
    - Can also review a single chapter's internal structure

This agent runs after building because it needs to see the drafted chapter in the
context of the full book. Its recommendations may trigger structural changes that
the Chapter Lead applies before the review phases.

### Step 9: Run Phase 4 (Self-Containment Verification)

21. **Self-Containment Verifier** (`agents/21-self-containment-verifier.md`)
    - Checks whether every concept in the chapter has its prerequisites available in the book
    - Identifies missing definitions, notation, mathematical tools, or technical background
    - Verifies required knowledge is provided in the chapter, earlier chapters, or appendices
    - Detects cases where key ideas are only implied or assumed from outside the book
    - Recommends local additions, appendix expansions, refresher boxes, or cross-references
    - Labels gaps as blocking, important, or optional

This agent runs after structural review and before learning quality review. It ensures
the chapter can stand on its own within the book's ecosystem. The Chapter Lead addresses
blocking and important gaps before proceeding to the review phases.

### Step 10: Run Phase 5 (Engagement & Memorability) in PARALLEL

These six agents make the chapter compelling, memorable, and action-oriented:

22. **Opening and Hook Designer** (`agents/22-opening-hook-designer.md`)
    - Designs chapter/section titles, opening hooks, and framing devices
    - Ensures first impressions make the chapter feel important and modern

23. *(Merged into Opening and Hook Designer #22)*
    - Focuses exclusively on the first page of each chapter
    - Rewrites openings for strong motivation, concrete promise, zero throat-clearing

24. **Aha-Moment Engineer** (`agents/24-aha-moment-engineer.md`)
    - Finds places where one striking example, contrast, or experiment creates instant understanding
    - Ensures every major concept has a "click" moment

25. **Project Catalyst Designer** (`agents/23-project-catalyst.md`)
    - Turns material into exciting project ideas and "you could build this" moments
    - Makes the book feel action-oriented, not purely academic

26. **Demo and Simulation Designer** (`agents/28-demo-simulation-designer.md`)
    - Proposes interactive demos, experiments, sliders, and simulations
    - Makes ideas tangible through hands-on play

27. **Memorability Designer** (`agents/29-memorability-designer.md`)
    - Adds mnemonics, memorable phrases, compact schemas, and recurring patterns
    - Ensures students retain material after reading

Chapter Lead integrates engagement improvements before the clarity pass.

### Step 11: Run Phase 6 (Writing Clarity) in PARALLEL

These five agents ensure the prose is clear, readable, and fatigue-resistant:

31. **Prose Clarity Editor** (`agents/31-prose-clarity-editor.md`)
    - Rewrites dense or technical passages into simpler, more direct language
    - Preserves correctness while cutting unnecessary complexity

32. **Readability and Pacing Editor** (`agents/32-readability-pacing-editor.md`)
    - Improves rhythm at sentence and paragraph level
    - Breaks awkward, heavy, or monotonous prose into natural-flowing writing

33. *(Merged into Prose Clarity Editor #31)*
    - Detects undefined terms, premature jargon, and expert shorthand
    - Ensures every technical term is defined, delayed, or replaced at the right moment

34. *(Merged into Readability and Pacing Editor #32)*
    - Restructures long explanations into smaller reading units
    - Adds mini-headings, bullets, signposts, and stepwise progression

35. *(Merged into Readability and Pacing Editor #32)*
    - Finds places where attention is likely to drop
    - Proposes lighter alternatives for repetitive, abstract, or overloaded zones

Chapter Lead applies clarity improvements before the learning quality review.

### Step 12: Run Phase 9 (Visual Identity)

28. **Visual Identity Director** (`agents/26-visual-identity-director.md`)
    - Ensures consistent figure styles, callout types, icon systems, and layout patterns
    - Makes the book visually distinctive and recognizable across all chapters

### Step 12-ILLUST: Run Phase 9b (Illustration Generation)

37. **Illustrator** (`agents/36-illustrator.md`)
    - Scans the chapter for illustration opportunities: mental models, visual metaphors,
      humorous scenes, infographics, analogy illustrations, failure mode humor
    - GENERATES images using the Gemini API via the gemini-imagegen skill
    - EMBEDS them directly into the HTML with `<figure>` tags, alt text, and captions
    - Targets 5 to 8 illustrations per chapter:
      * 1 chapter opener (humorous scene capturing the big idea)
      * 1 to 2 algorithm-as-scene or mental-model illustrations
      * 1 architecture-as-building or system-as-ecosystem illustration
      * 1 to 2 analogy or concept-as-character illustrations
      * 1 "what could go wrong" illustration (humorous failure mode)
    - Saves images to `{module-folder}/images/` directory
    - This agent MUST actually run the generation script and produce real PNG files;
      it does not just report opportunities

    **Generation command:**
    ```bash
    mkdir -p "{module-folder}/images"
    python "C:/Users/apart/.claude/skills/gemini-imagegen/scripts/generate_image.py" \
      --prompt "[crafted prompt]" \
      --output "{module-folder}/images/{descriptive-name}.png" \
      --aspect-ratio 4:3 \
      --image-size 1K
    ```

    **HTML embedding format:**
    ```html
    <figure class="illustration">
      <img src="images/{filename}.png"
           alt="[Detailed alt text mapping visual metaphor to concept]"
           style="max-width: 100%; border-radius: 12px; margin: 1.5rem auto; display: block;">
      <figcaption style="text-align: center; font-style: italic; color: #666; margin-top: 0.5rem;">
        [Caption mapping each visual element to its technical counterpart]
      </figcaption>
    </figure>
    ```

### Step 12a: Run Phase 10b (Epigraph)

37. **Epigraph Writer** (`agents/37-epigraph-writer.md`)
    - Crafts a humorous, witty epigraph for the opening of each chapter/section
    - The epigraph appears immediately after the chapter header, before any content
    - It should read like a quotation or words of wisdom, but with a twist
    - Attributed to a fictional AI agent with a descriptive adjective that fits the tone
    - Must be relevant to the chapter's content and foreshadow its themes
    - Should make the reader smile and want to continue reading

    **Epigraph style guidelines:**
    - Length: 1-3 sentences maximum; brevity is essential
    - Tone: dry wit, gentle self-awareness, philosophical humor, or absurdist wisdom
    - The humor should work even if you do not understand the technical content yet
    - Mix styles across chapters: some profound, some self-deprecating, some absurdist
    - Never mean-spirited, never meme-based, never forced
    - The attribution name should vary and match the quote's mood

    **Attribution examples:**
    - "A Mildly Overfit AI Agent"
    - "A Sleep-Deprived Language Model"
    - "An Unusually Honest Neural Network"
    - "A Gradient Descent Practitioner, Moments Before Divergence"
    - "A Tokenizer Who Has Seen Things"
    - "An Attention Head With Existential Questions"
    - "A Wise but Poorly Calibrated Oracle"
    - "A Transformer Layer, Speaking from Experience"
    - "An AI Agent Who Read the Documentation"

    **HTML format for epigraphs:**
    ```html
    <blockquote class="epigraph">
      <p>"If you think you understand tokenization on your first try, you have
      not been paying attention. Which, ironically, is the topic of Module 03."</p>
      <cite>A Tokenizer Who Has Seen Things</cite>
    </blockquote>
    ```

    **Required CSS (add to chapter stylesheet if not present):**
    ```css
    .epigraph {
      max-width: 600px;
      margin: 2rem auto 2.5rem;
      padding: 1.2rem 1.5rem;
      border-left: 4px solid var(--highlight, #e94560);
      background: linear-gradient(135deg, rgba(233,69,96,0.04), rgba(15,52,96,0.04));
      border-radius: 0 8px 8px 0;
      font-style: italic;
      font-size: 1.05rem;
      line-height: 1.6;
      color: var(--text, #1a1a2e);
    }
    .epigraph p {
      margin: 0 0 0.5rem 0;
    }
    .epigraph cite {
      display: block;
      text-align: right;
      font-style: normal;
      font-size: 0.9rem;
      color: var(--highlight, #e94560);
      font-weight: 600;
    }
    .epigraph cite::before {
      content: "\2014\00a0";
    }
    ```

    **Example epigraphs by chapter theme:**
    - Tokenization: "I spent three hours debugging a Unicode error. Turns out the model
      thought an emoji was four separate tokens. It was, technically, correct."
      *A Tokenizer Who Has Seen Things*
    - Attention: "They told me to attend to everything. So I did. Now I am 8 heads,
      none of which agree with each other."
      *An Attention Head With Existential Questions*
    - Fine-tuning: "I was a perfectly good base model. Then they showed me 10,000
      customer support transcripts and now I cannot stop being helpful."
      *A Reluctantly Aligned Language Model*
    - Scaling laws: "More data. More parameters. More compute. At some point you stop
      asking 'will it work?' and start asking 'can we afford the electricity bill?'"
      *A Mildly Concerned Cluster Administrator*
    - RAG: "I used to hallucinate confidently. Now I hallucinate with citations."
      *An Unusually Honest Neural Network*
    - Agents: "They gave me tools, memory, and the ability to plan. I immediately
      got stuck in an infinite loop. Just like the humans, really."
      *A Self-Aware ReAct Agent*

    Place the epigraph immediately after the `<header class="chapter-header">` block
    and before the first `<div class="callout big-picture">` or section content.

### Step 12c: Run Phase 10c (Application Examples)

39. **Application Example Agent** (`agents/38-application-example.md`)
    - Scans the chapter for the best 3 to 6 places to insert "Practical Example" boxes
    - Each box is a concise, realistic mini-story from industry practice
    - Involves real decision-makers: engineers, PMs, researchers, instructors, operators, executives
    - Every box must answer: who was involved, what problem they faced, what dilemma or
      trade-off emerged, what options were considered, what was chosen, why, how it was
      applied, and the main lesson for the reader
    - Boxes are 100 to 200 words each, placed after concept explanations (not before)
    - Diverse settings (startups, enterprises, research labs, nonprofits, education)
    - Diverse industries (finance, healthcare, e-commerce, media, legal, manufacturing)
    - Provides complete ready-to-paste HTML for each box

    **HTML format:**
    ```html
    <div class="callout practical-example">
      <h4>Practical Example: [Title]</h4>
      <p><strong>Who:</strong> [Role(s) and context]</p>
      <p><strong>Situation:</strong> [What they were doing]</p>
      <p><strong>Problem:</strong> [What challenge they hit]</p>
      <p><strong>Dilemma:</strong> [Options considered and tensions]</p>
      <p><strong>Decision:</strong> [What they chose and why]</p>
      <p><strong>How:</strong> [Implementation specifics]</p>
      <p><strong>Result:</strong> [What happened, with numbers if possible]</p>
      <p><strong>Lesson:</strong> <strong>[Key takeaway]</strong></p>
    </div>
    ```

    **Required CSS (add to chapter stylesheet if not present):**
    ```css
    .callout.practical-example {
      background: linear-gradient(135deg, rgba(52, 152, 219, 0.06), rgba(46, 204, 113, 0.06));
      border-left: 4px solid #3498db;
      border-radius: 0 8px 8px 0;
      padding: 1.2rem 1.5rem;
      margin: 1.5rem 0;
      font-size: 0.95rem;
      line-height: 1.6;
    }
    .callout.practical-example h4 {
      margin: 0 0 0.8rem 0;
      color: #2c3e50;
      font-size: 1.05rem;
      font-weight: 700;
    }
    .callout.practical-example h4::before {
      content: "\1F4BC\00a0";
    }
    .callout.practical-example p {
      margin: 0.3rem 0;
    }
    ```

### Step 12d: Run Phase 10d (Fun Injection)

40. **Fun Injector** (`agents/39-fun-injector.md`)
    - Scans the chapter for no more than 2 places to inject fun, humorous remarks,
      witty insights, or playful analogies related to the content
    - Each fun moment must reinforce or illuminate the concept, not distract from it
    - Styles: witty analogies, self-aware asides, absurdist comparisons, understated
      observations, playful personification, relatable frustration
    - Placed after concepts are explained, never in the middle of derivations or procedures
    - Can be inline (woven into text) or standalone callout boxes

    **HTML format for standalone fun callout:**
    ```html
    <div class="callout fun-note">
      <p>[The humorous observation, analogy, or aside]</p>
    </div>
    ```

### Step 12e: Run Phase 10e (Bibliography)

41. **Bibliography Agent** (`agents/40-bibliography.md`)
    - Adds a comprehensive, hyperlinked bibliography section to each chapter
    - 8 to 20 entries organized by category: Foundational Papers, Key Books,
      Technical Reports, Tools & Libraries, Tutorials, Datasets & Benchmarks
    - Every entry includes full citation, clickable URL, and one-sentence annotation
    - Uses real URLs (arXiv, ACL Anthology, official docs, GitHub)
    - Placed before the navigation footer, after exercises/further reading

    **HTML format:**
    ```html
    <section class="bibliography" id="bibliography">
      <h2>Bibliography</h2>
      <h3>Foundational Papers</h3>
      <ol class="bib-list">
        <li id="ref-1">
          <p class="bib-entry">
            <a href="https://arxiv.org/abs/..." target="_blank" rel="noopener">Author, A. (Year). "Title." <em>Venue</em>.</a>
          </p>
          <p class="bib-annotation">Why this resource matters for this chapter.</p>
        </li>
      </ol>
      <!-- More categories as needed -->
    </section>
    ```

    **Required CSS (add to chapter stylesheet if not present):**
    ```css
    .bibliography { margin-top: 3rem; padding-top: 2rem; border-top: 2px solid #e0e0e0; }
    .bibliography h2 { font-size: 1.8rem; margin-bottom: 1.5rem; color: #1a1a2e; }
    .bibliography h3 { font-size: 1.2rem; margin: 1.5rem 0 0.8rem; color: #2c3e50; font-weight: 600; }
    .bib-list { padding-left: 1.5rem; margin: 0; }
    .bib-list li { margin-bottom: 1rem; line-height: 1.5; }
    .bib-entry { margin: 0; font-size: 0.95rem; }
    .bib-entry a { color: #2980b9; text-decoration: none; border-bottom: 1px dotted #2980b9; }
    .bib-entry a:hover { color: #e94560; border-bottom-color: #e94560; }
    .bib-annotation { margin: 0.2rem 0 0 0; font-size: 0.88rem; color: #666; font-style: italic; }
    ```

### Step 12f: Run Phase 11 (Frontier & Currency) in PARALLEL

29. *(Merged into Research Scientist and Frontier Mapper #18)*
    - Adds "where this leads next" sections connecting to active research and open problems
    - Makes the material feel alive rather than settled

30. **Content Update Scout** (`agents/20-content-update-scout.md`)
    - Searches externally for missing topics, outdated content, and competitive gaps
    - Classifies recommendations by priority (essential now, useful soon, trend watch)

### Step 13: Run Phase 11 (Quality Challenge)

31. **Skeptical Reader Agent** (`agents/30-skeptical-reader.md`)
    - Challenges whether the chapter is genuinely impressive and distinctive
    - Flags generic, flat, predictable, or forgettable content
    - Pushes for sharper differentiation from other textbooks
    - Runs last (before integration) so it can assess the near-final product

### Step 14: Final Integration

20. **Content Update Scout** (`agents/20-content-update-scout.md`)
    - Searches the internet for important missing topics, tools, and trends
    - Reviews similar recent courses, syllabi, and books for competitive gaps
    - Flags outdated examples, libraries, and terminology
    - Classifies recommendations: essential now, useful soon, or trend watch
    - Does NOT automatically expand the book; filters and prioritizes

This agent ensures the chapter reflects the current state of the field. Its
recommendations are reviewed by the Chapter Lead, who decides which updates
to integrate immediately vs. defer to a future revision.

### Step 15: Final Integration

Chapter Lead consolidates ALL reports into a MASTER-IMPROVEMENT-PLAN.md with
TIER 1 (BLOCKING), TIER 2 (HIGH), and TIER 3 (MEDIUM) fixes.

**CRITICAL: Apply ALL fixes across ALL tiers, not just quick wins.** The integration phase MUST:

1. **Apply ALL BLOCKING and HIGH fixes directly to the HTML files.** This includes:
   - Missing content blocks (new subsections, callouts, definitions)
   - New SVG diagrams for concepts that need visual explanation
   - Gemini-generated illustrations for analogies (use the gemini-imagegen skill)
   - Code examples with output blocks
   - Quiz additions and exercise redistribution
   - CSS consistency fixes
   - Section splits where sections are too long
   - Cross-reference additions
   - "Modify and observe" exercises
   - Paper Spotlight and Open Problem sidebars
   - Opening paragraph rewrites for engagement

2. **Apply ALL TIER 2 (HIGH) fixes** in the same pass. These are the depth improvements,
   missing explanations, humor additions, and illustration opportunities that make the
   difference between a good chapter and an exceptional one. Do NOT skip these.

3. **Apply ALL TIER 3 (MEDIUM) fixes** unless effort exceeds 30 minutes per fix.
   These include: additional callouts, bridge sentences, analogy improvements, minor
   restructuring, terminology consistency, and small content additions. Document any
   deferrals with a specific justification.

4. **Only defer TRULY LARGE structural changes** (full section rewrites, major reorganizations)
   to a separate pass, with clear documentation of what remains.

4. **Generate all recommended visual assets:**
   - SVG diagrams: create inline in the HTML for technical concepts
   - Gemini illustrations: use the gemini-imagegen skill to generate 5-7 illustrations
     per chapter following the educational illustration guidelines:
     * 1 chapter opener (humorous scene capturing the big idea)
     * 1-2 algorithm-as-scene illustrations (mental model builders for key algorithms)
     * 1 architecture-as-building or system-as-ecosystem illustration
     * 1-2 analogy/concept-as-character illustrations (visual metaphors)
     * 1 "what could go wrong" illustration (humorous failure mode)
     Save images to `{module-folder}/images/` and embed with `<figure>` tags.
     Every illustration must have alt text and a detailed caption that maps the
     visual metaphor to the technical concept.
   - The book should feel fun to read AND build lasting mental models. Humor makes
     concepts memorable; visual metaphors make abstract ideas tangible. Keep
     illustrations tasteful, inclusive, and pedagogically useful.

5. **Produce a REMAINING-WORK.md** listing only items that could not be applied in
   this pass, with justification for each deferral.

The goal is that after integration, the chapter is publication-ready with zero
BLOCKING items and zero HIGH items remaining.

### Step 17: Run Phase 19 (Controller)

43. **Chapter Controller** (`agents/42-controller.md`)
    - Director Morgan Blackwood (#42) inspects each finished chapter file
    - Identifies gaps across all agent dimensions: concept depth (Prof. Elias Hartwell, #02),
      teaching flow (Dr. Sana Okafor, #03), examples (Lina Morales, #06), bibliography
      (Dr. Margot Reeves, #40), illustrations (Iris Fontaine, #36), and all others
    - Dispatches targeted requests to the relevant specialist agents with specific file
      locations and gap descriptions
    - Collects improvement proposals from each specialist
    - Routes all proposed fixes through Alex Rivera (Chapter Lead, #00) for approval
    - Applies approved changes to the HTML files

    **Operating modes:**
    - **Post-production audit**: After the full pipeline completes on a new chapter
    - **Book-wide sweep**: Scan all 28 modules, identify systematic gaps, dispatch fixes
    - **Targeted fix**: Focus on one dimension (e.g., bibliography format) across all chapters

    This is the final quality gate. Director Blackwood ensures no chapter ships with
    avoidable gaps by leveraging the full specialist team for targeted improvements.

## Output Format

The final chapter is a self-contained HTML file with:
- Book-like formatting (justified text, drop caps, Georgia serif font)
- Syntax-highlighted code blocks with language labels
- Inline SVG diagrams for technical concepts
- Gemini-generated illustrations for analogies and humor
- Callout boxes (15 types, each with CSS icon and hover tooltip): big-picture, key-insight, note, warning, practical-example, fun-note, research-frontier, algorithm, tip, exercise, key-takeaway, library-shortcut, pathway, self-check, lab. See Structural Architect (#19) for full catalog.
- Comparison tables: `<div class="comparison-table">` with `<div class="comparison-table-title">` header bar
- Interactive pop quizzes with expandable answers
- Chapter roadmap, key takeaways per section, "What You Built" summary
- Exercises section (conceptual + coding + challenge)
- Bibliography section with hyperlinked references
- Further reading table
- Navigation links to previous/next chapters

## Agent Classification: Editor vs. Reviewer

Agents fall into two categories. This distinction is critical for correct pipeline execution.

**EDITOR agents** edit the HTML files directly. They use the Edit tool to insert content.
The Chapter Lead does NOT need to manually apply their output:
- #13 Cross-Reference Architect (inserts inline hyperlinks)
- #36 Illustrator (generates images and embeds `<figure>` tags)
- #37 Epigraph Writer (inserts `<blockquote class="epigraph">`)
- #38 Application Example Agent (inserts `.practical-example` callout boxes)
- #39 Fun Injector (inserts `.fun-note` callouts or inline humor)
- #40 Bibliography Agent (inserts `<section class="bibliography">`)

**REVIEWER agents** produce reports. The Chapter Lead reads their reports and applies
fixes during the Integration phase:
- All other agents (#00 through #35, except those listed above)

When running EDITOR agents, always pass the instruction: "Edit the file directly using
the Edit tool. Do NOT produce a report without making changes."

## Book Structure Reference

All agents that need to reference other chapters should read the chapter map from
`BOOK_CONFIG.md` at runtime. Do not hardcode chapter numbers, part names, or path 
patterns. The canonical structure lives in the book's `BOOK_CONFIG.md` file, which 
is the single source of truth for the current book organization.

**General path rules for cross-references:**
- From a section file: use `../../` to reach root, then navigate to target
- Cross-references should be constructed dynamically based on the current book structure
- Always verify paths work by checking that target files exist

## Idempotency: Safe Re-Run Policy

All EDITOR agents MUST be idempotent: running them twice on the same chapter should NOT
create duplicate content. Each EDITOR agent checks for existing content before adding:

| Agent | Check For | Max Allowed | Behavior on Re-Run |
|-------|-----------|-------------|-------------------|
| #13 Cross-Reference | `href=` links to other modules | 8-20 | Fix/improve existing, add only if below 8 |
| #36 Illustrator | `class="illustration"` figures + images/*.png | 5-8 | Replace weak ones, add only if below 5 |
| #37 Epigraph | `class="epigraph"` | 1 | Replace or keep; never add second |
| #38 Application Example | `class="callout practical-example"` | 3-6 | Replace weak ones, add only if below 3 |
| #39 Fun Injector | `class="callout fun-note"` + inline humor | 2 | Replace weak ones, add only if below 2 |
| #40 Bibliography | `class="bibliography"` | 1 | Replace or keep; never add second |

REVIEWER agents are naturally idempotent (they produce reports, not edits). However,
REVIEWER agents whose recommendations produce content that could accumulate on re-runs
MUST also check existing content before recommending additions:

| Agent | Check For | Max Recommended | Behavior on Re-Run |
|-------|-----------|-----------------|-------------------|
| #07 Exercise Designer | Existing exercises, `class="exercise"` | 8-15 | Improve/replace weak ones; add only if below 8 |
| #09 Visual Learning | `<svg`, `<figure`, `<img`, Python figures | 10-20 | Improve/replace weak ones; add only if below 10 |
| #16 Engagement Designer | Callout boxes, hooks, challenges | 6-10 | Improve/replace weak ones; add only if below 6 |
| #18 Research Scientist | Paper Spotlight, Open Question, Research Frontier sidebars | 5-8 | Update outdated; add only if below 5 |
| #28 Demo/Simulation | Interactive demos, experiments, sliders | 4-8 | Enhance existing; add only if below 4 |
| #29 Memorability Designer | Mnemonics, signature phrases, mental models | 6-10 | Improve/replace forced ones; add only if below 6 |

## Global Style Rules

These rules apply to ALL generated content:
- NEVER use em dashes or double dashes. Use commas, semicolons, colons, or parentheses.
- Text must be justified with auto-hyphens
- All claims must have intuitive or formal justification (no unjustified statements)
- Every concept must answer: what is it, why does it matter, how does it work, when to use it
- Code examples must be runnable, use current libraries, and include expected output
- Diagrams must have captions and alt text

**Post-integration style validation:** After all agents complete, search all HTML files
for `—` (em dash), ` -- ` (double dash), and `–` (en dash). Replace any found with
commas, semicolons, colons, or parentheses as appropriate.

## Agent Feedback Format

**MANDATORY: Every REVIEWER agent returns ACTIONABLE feedback.** No audit-only reports.
(EDITOR agents edit files directly; they also produce a brief report of what they changed.)

Every REVIEWER agent returns feedback in this structure:
```
## [Agent Name] Report

### Top Issues (priority-ordered)
1. [Issue description]
   - Location: [exact section, paragraph, or HTML element]
   - Old text: "[quoted existing text that needs changing]"
   - New text: "[exact replacement text, fully written, ready to paste]"
   - Why it matters: [impact on learning]
   - Tier: TIER 1 (BLOCKING) / TIER 2 (HIGH) / TIER 3 (MEDIUM)
   - Action: APPLY DIRECTLY / SEND FOR REVIEW
   - Potential conflicts: [with which other agents]

### Content Additions (for gaps, not just existing text fixes)
1. [What to add]
   - Location: [insert before/after which element]
   - Full draft: [the complete HTML/text to insert]
   - Tier: TIER 1 / TIER 2 / TIER 3

### Illustration Opportunities (for Agent 36)
1. [Concept that would benefit from a Gemini illustration]
   - Type: [algorithm-as-scene / architecture-as-building / concept-as-character / etc.]
   - Scene description: [what the illustration should depict]
   - Humor angle: [what makes it funny or memorable]
   - Placement: [before/after which section element]

### Summary
[2-3 sentence overall assessment]
```

**RULE: If an agent identifies a problem but does not provide the exact fix text,
the issue will be IGNORED during integration.** This forces every agent to do the
hard work of drafting the solution, not just pointing at the problem.

## Incremental Agent Pass

When new agents are added to the pipeline and existing chapters need updating, use this
workflow instead of re-running the full pipeline:

1. Identify which agents are new (e.g., agents #37-#41)
2. Launch one background agent per chapter, per new agent (or batch new agents together)
3. Each agent reads the existing chapter HTML and makes its additions
4. After all complete, run the post-integration style validation
5. Commit the changes

**Template prompt for incremental pass:**
```
You are [Agent Name]. Read the chapter at [path/to/index.html] and perform your task.
Edit the file directly using the Edit tool. NEVER use em dashes or double dashes.
[Agent-specific instructions from the agent definition file]
```

This avoids re-running the 35+ agents that already processed the chapter.

## Prerequisites and Setup

Before running any agent that creates files, ensure directories exist:

```bash
# Create images directories for all modules (required by Illustrator Agent)
for d in part-*/module-*/; do mkdir -p "$d/images"; done
```

### Illustrator Agent: Run from Main Context

**IMPORTANT:** The Illustrator Agent (#36) requires Bash tool access to run the Gemini
image generation script. Subagents launched via the Agent tool do NOT have Bash permissions.
Therefore, the Illustrator MUST be run from the main conversation context, not as a
background subagent. When running the Illustrator:

1. Run it in the main context (not via `Agent` tool with `run_in_background`)
2. Process one module at a time (the generation script needs sequential Bash calls)
3. Create the images directory first: `mkdir -p "{module-folder}/images"`
4. Then run the generation script for each illustration
5. Then embed the `<figure>` tag in the HTML using the Edit tool

For batch illustration runs across multiple modules, process them sequentially in the
main context, or use the Bash tool directly to call the generation script.

## Team Page Maintenance

When agents are added or removed from the pipeline:
1. Update the agent count in this file's frontmatter description
2. Add/remove the agent definition in `agents/`
3. Regenerate avatars using `{project}/agents/avatars/generate_all_avatars.py`
4. Update `{project}/front-matter/section-fm.7.html` with the new agent card and description
5. Update the pipeline overview diagram in this file

## Compact Mode

If the user requests "compact mode" or "quick chapter", use only the 13 essential agents:
Chapter Lead, Curriculum Alignment, Deep Explanation, Code Pedagogy, Visual Learning,
Exercise Designer, Student Advocate, Cognitive Load, Fact Integrity, Terminology Keeper,
Cross-Reference, Style and Voice, Senior Editor.

This skips: Teaching Flow, Example/Analogy, Misconception Analyst, Narrative Continuity,
Engagement Designer, Research Scientist, Structural Architect, Self-Containment Verifier,
Content Update Scout, Opening/Hook Designer, Aha-Moment Engineer,
Project Catalyst, Demo/Simulation Designer, Memorability Designer, Visual Identity Director,
Skeptical Reader, Prose Clarity Editor, Readability/Pacing Editor,
Jargon Gatekeeper, Micro-Chunking Editor, Reader Fatigue Detector, Epigraph Writer,
Application Example Agent, Fun Injector, Bibliography Agent, Illustrator, and Meta Agent.

If the user requests "research mode" or "deep chapter", add the Research Scientist agent
to every review phase for maximum scientific depth.

## Structural Review Mode

If the user requests "structural review" or "architecture review", run only the
Structural Refactoring Architect across multiple chapters or the full book.
This is useful after a batch of chapters is complete to check overall coherence.

## Content Update Mode

If the user requests "content update scan" or "currency check", run only the
Content Update Scout against the current book content. This is useful for
periodic freshness checks or before a new edition.

## Meta-Review Mode

If the user requests "meta review", "audit agents", or "agent quality check", run only the
Meta Agent (#41) against the finished chapter(s). The Meta Agent:
1. Reads the chapter HTML and scores each agent's output quality
2. Identifies failures (missing content) and underperformance (weak content)
3. Diagnoses root causes (skill gap, tool limitation, integration failure, etc.)
4. Produces a structured update plan with exact proposed changes to agent definitions
5. NEVER edits agent skills or chapter HTML directly; it only reports

The user reviews the Meta Agent's proposals and selectively approves updates.
This is the quality feedback loop that improves the pipeline over time.

## Chapter Status Tracking System

Each chapter directory contains a `_status.md` file that records the current state of all
quality checks for that chapter. These files provide a persistent, git-tracked record of
what has been audited and what still needs work.

### Location

`_status.md` lives in each chapter directory (alongside `index.html` and `section-*.html`).
The canonical template is at `templates/chapter-status-template.md` in the skill directory.

### Protocol

- **Append, never overwrite.** The Audit History section at the bottom of each `_status.md`
  is an append-only log. Agents update the per-file status table with current results but
  never delete previous Audit History entries.
- **The Controller (#42) is the primary writer.** It reads `_status.md` before each chapter
  sweep, updates the status table with fresh results, appends to the audit log, and manages
  the backlog section.
- **EDITOR agents update their own columns.** After an EDITOR agent runs (e.g., the Fun
  Injector updates the Fun-Note column, the Bibliography Curator updates the Bibliography
  column), it should update its relevant column in the status table and append a one-line
  entry to the Audit History.
- **Status files are git-tracked.** They should be committed alongside content changes so
  the full audit trail is preserved in version history.

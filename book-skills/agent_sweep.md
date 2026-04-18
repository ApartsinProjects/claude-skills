# Agent Sweep Execution Plan

Optimal strategy for applying the 42-agent book-writing pipeline to all section files.

## Scale

- 10 Parts, 36 Modules, ~449 section HTML files
- 22 appendix directories, ~106 appendix section files
- **Total: ~555 content HTML files**
- 42 agent skill files (numbered 00-41)

## Agent Classification

### Editor Agents (modify HTML directly)

| #   | Agent                     | What It Edits                           |
| --- | ------------------------- | --------------------------------------- |
| 13  | Cross-Reference Architect | Inserts `<a>` tags throughout           |
| 25  | Visual Identity Director  | CSS/styling fixes                       |
| 31  | Illustrator               | Generates PNGs, embeds `<figure>` tags  |
| 32  | Epigraph Writer           | Inserts `<blockquote class="epigraph">` |
| 33  | Application Example       | Inserts `.callout.practical-example`    |
| 34  | Fun Injector              | Inserts `.callout.fun-note`             |
| 35  | Bibliography Curator      | Inserts/updates `.bibliography`         |
| 37  | Controller                | Structural/formatting fixes             |
| 39  | Figure Fact Checker       | Fixes SVG/figure errors                 |
| 40  | Code Caption Agent        | Adds/fixes code captions                |

### Reviewer Agents (produce reports, Chapter Lead integrates)

01 Curriculum Alignment, 02 Deep Explanation, 03 Teaching Flow, 04 Student Advocate,
05 Cognitive Load, 06 Example/Analogy, 07 Exercise Designer, 08 Code Pedagogy,
09 Visual Learning, 10 Misconception Analyst, 11 Fact Integrity, 12 Terminology Keeper,
14 Narrative Continuity, 15 Style/Voice, 16 Engagement, 17 Senior Editor,
18 Research Scientist, 19 Structural Architect, 20 Content Update Scout,
21 Self-Containment Verifier, 22 Opening/Hook, 23 Project Catalyst,
24 Aha-Moment, 26 Demo/Simulation, 27 Memorability, 28 Skeptical Reader,
29 Prose Clarity, 30 Readability/Pacing

### Meta Agents (audit pipeline, not content)

| #   | Agent          | Scope                                            |
| --- | -------------- | ------------------------------------------------ |
| 00  | Chapter Lead   | Orchestrates per chapter                         |
| 36  | Meta Agent     | Audits agent performance, proposes skill updates |
| 38  | Publication QA | Browser-based rendering verification             |



## Execution Phases

### Phase 1: Preparation (serial, one-time)

Read `BOOK_CONFIG.md`, `CROSS_REFERENCE_MAP.md`, `CONFORMANCE_CHECKLIST.md`.

### Phase 2: Structural Foundation

**Must complete before content work.**

Agents: `#37` Controller (direct fix sweep) + `#40` Code Caption Agent

- Fix header links, CSS classes, nav footers, inline style removal, element ordering
- Add numbered captions to all code blocks
- These two can run in parallel (non-overlapping HTML regions)
- **All 10 batches in parallel**
- Invocations: 10 batches x 2 agents = **20**

### Phase 3: Section-Level Content Review (read-only, massively parallel)

All reviewer agents run in parallel, all batches in parallel. No file conflicts.

| Agent | What It Checks                                                 |
| ----- | -------------------------------------------------------------- |
| 02    | Concept depth (what/why/how/when)                              |
| 03    | Transitions, pacing, prose around code/tables/diagrams         |
| 04    | Jargon, clarity, assumed knowledge, tri-audience balance       |
| 05    | Concept velocity, wall-of-text, rest stops                     |
| 06    | Concrete examples for abstract concepts                        |
| 08    | Runnable code, pedagogical context, library shortcuts          |
| 10    | Common pitfalls and misconceptions                             |
| 11    | Factual accuracy                                               |
| 15    | Tone consistency                                               |
| 16    | Monotony detection, engagement elements                        |
| 18    | Research frontier callouts, paper spotlights, library currency |
| 20    | Content currency (stale claims, deprecated APIs)               |

- Invocations: 12 agents x 10 batches = **120** (all parallel)

### Phase 4: Chapter-Level Review (read-only, parallel by chapter)

These agents need multi-section context within a single module.

| Agent | Why Full Chapter Needed                                   |
| ----- | --------------------------------------------------------- |
| 01    | Learning objectives vs actual coverage                    |
| 14    | Story arc, thread continuity across sections              |
| 17    | Holistic editorial judgment, box overload, visual balance |
| 21    | Prerequisite satisfaction within chapter                  |
| 22    | Chapter opener quality, first section delivery            |
| 28    | Skeptical challenge of chapter's distinctiveness          |

- Invocations: 6 agents x 36 chapters = **216** (all parallel, read-only)

### Phase 5: Cross-Chapter Review (read-only, book-wide)

These agents compare content across different chapters.

| Agent | Cross-Chapter Concern                                   |
| ----- | ------------------------------------------------------- |
| 12    | Terminology consistency, synonym drift, notation        |
| 13    | Link graph analysis (Audit mode), bidirectional linking |
| 19    | Duplicate content detection, dependency analysis        |
| 21    | Prerequisite chain tracing across the full book         |

- Invocations: **4** (parallel, each reads full book)

### Phase 6: Integration (Chapter Lead applies all feedback)

`#00` Chapter Lead (Implement mode): merges all reviewer feedback from Phases 3-5, resolves conflicts, applies fixes. Includes tri-audience checkpoint.

- Invocations: **36** (parallel by chapter, each edits only its own files)

### Phase 7: Content Enrichment (editor agents, sequential within file set)

Editor agents that insert content into the same HTML file must run sequentially.

**Step 7a** (parallel within step, all 10 batches):

- `#32` Epigraph Writer (top of file)
- `#33` Application Example Designer (after concept explanations)
- `#34` Fun Injector (at natural break points)
- These edit different regions; can run together

**Step 7b** (10 batches in parallel):

- `#35` Bibliography Curator (bottom of file)

**Step 7c** (10 batches in parallel):

- `#13` Cross-Reference Architect (Implement mode, inserts `<a>` tags throughout)

- Invocations: 3 steps x 10 batches = **30**

### Phase 8: Illustration (asset generation then embedding)

**Gate 8a**: Image Generation (creates new PNGs, no HTML edits)

- `#31` Illustrator (Generate mode): 5-8 images per chapter
- 36 chapters in parallel

**Gate 8b**: Image Embedding (edits section HTML)

- `#31` Illustrator (Embed mode): insert generated images
- 10 batches in parallel

**Gate 8c**: Figure Verification

- `#39` Figure Fact Checker: verify all figures/SVGs

- 10 batches in parallel

- Invocations: 36 + 10 + 10 = **56**

### Phase 9: Polish and Clarity

**Gate 9a**: Writing Clarity (reviewer, then Chapter Lead applies)

- `#29` Prose Clarity Editor + `#30` Readability/Pacing Editor
- 10 batches, both agents parallel
- Invocations: **20**

**Gate 9b**: Visual Identity

- `#25` Visual Identity Director
- 10 batches in parallel
- Invocations: **10**

**Gate 9c**: Engagement and Memorability (reviewer)

- `#22` Opening/Hook, `#23` Project Catalyst, `#24` Aha-Moment, `#26` Demo/Simulation, `#27` Memorability
- All parallel, all batches parallel
- Invocations: **50**

### Phase 10: Validation

**Gate 10a**: Post-Integration Verification

- `#37` Controller (full sweep): em dashes, broken links, CSS, structural compliance
- 10 batches in parallel

**Gate 10b**: Meta Review

- `#36` Meta Agent: audit agent performance, propose skill updates
- 1 book-wide invocation

**Gate 10c**: Publication QA

- `#38` Publication QA: browser-based rendering check

- 10 per-part invocations

- Invocations: 10 + 1 + 10 = **21**

### Phase 11: Appendices (parallel track)

Appendices follow the same pipeline (Phases 3-10) but can begin after Phase 2 completes. They have their own batch (K) and do not conflict with chapter files.

- Invocations: ~**100** (proportional to 106 appendix files)

## Dependency Graph

```
Phase 1 (Prep)
    |
Phase 2 (Structural) ────────────────────────────────────┐
    |                                                     |
Phase 3 (Section Review) ──┐                     Phase 11 (Appendices,
Phase 4 (Chapter Review) ──┤                      same pipeline on
Phase 5 (Cross-Chapter) ───┘                      Batch K, parallel)
    |
Phase 6 (Integration)
    |
Phase 7a (Epigraph + Examples + Fun)
    |
Phase 7b (Bibliography)
    |
Phase 7c (Cross-References)
    |
Phase 8a (Image Generation)
    |
Phase 8b (Image Embedding)
    |
Phase 8c (Figure Verification)
    |
Phase 9a (Prose Clarity) ──┐
Phase 9b (Visual Identity) ┤
Phase 9c (Engagement) ─────┘
    |
Phase 10a (Controller Sweep)
    |
Phase 10b (Meta Review)
    |
Phase 10c (Publication QA)
```

## Invocation Summary

| Phase     | Description            | Invocations | Max Parallelism    |
| --------- | ---------------------- | ----------- | ------------------ |
| 2         | Structural Conformance | 20          | 10-way             |
| 3         | Section-Level Review   | 120         | 120-way            |
| 4         | Chapter-Level Review   | 216         | 216-way            |
| 5         | Cross-Chapter Review   | 4           | 4-way              |
| 6         | Integration            | 36          | 36-way             |
| 7         | Enrichment Editors     | 30          | 10-way per step    |
| 8         | Illustration           | 56          | 36-way then 10-way |
| 9         | Polish/Clarity         | 80          | 50-way             |
| 10        | Validation             | 21          | 10-way             |
| 11        | Appendices             | ~100        | parallel with main |
| **Total** |                        | **~683**    |                    |

## Critical Path Estimate

Assuming ~5 min per agent invocation with unlimited parallelism:

| Step                                   | Duration       |
| -------------------------------------- | -------------- |
| Phase 2 (structural)                   | 5 min          |
| Phases 3+4+5 (reviews, parallel)       | 5 min          |
| Phase 6 (integration)                  | 10 min         |
| Phase 7 (enrichment, 3 serial steps)   | 15 min         |
| Phase 8 (illustration, 3 serial gates) | 15 min         |
| Phase 9 (polish, parallel gates)       | 5 min          |
| Phase 10 (validation)                  | 10 min         |
| **Total critical path**                | **~65-80 min** |

With practical concurrency of 5-10 simultaneous agents: **4-6 hours**.

## Idempotency Rules

Every editor agent must check if its output already exists before inserting:

| Agent | Check Before Insert                                                      |
| ----- | ------------------------------------------------------------------------ |
| 32    | Existing `<blockquote class="epigraph">`; replace, do not duplicate      |
| 33    | Count `.callout.practical-example`; only add if below 3-6 per chapter    |
| 34    | Count `.callout.fun-note`; target max 2 per section file                 |
| 35    | Existing `.bibliography` section; update entries, do not duplicate       |
| 13    | Existing link to target within 500 words; do not double-link             |
| 40    | Existing `div.code-caption` after code block; update, do not add second  |
| 31    | Existing `<figure>` for concept; do not generate duplicate illustrations |
| 37    | Re-read file before every edit (re-read before edit rule)                |

## Safe Re-Run Protocol

1. **Before any re-run**: `git diff --stat` to identify changed files
2. **Targeted re-runs**: only re-run agents on files that need work
3. **Commit after each phase gate**: creates restore points
4. **Conflict detection**: after parallel gates, inspect files edited by multiple agents

## Four Scope Levels

| Scope             | What It Catches                                            | Agents                                            |
| ----------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| **Section**       | Content quality, code, captions, structure within one file | 02-06, 08-11, 15-16, 18, 20, 25, 29-35, 37, 39-40 |
| **Chapter**       | Narrative arc, objective coverage, exercise distribution   | 00, 01, 07, 14, 17, 21, 22, 28                    |
| **Cross-chapter** | Terminology drift, duplicate content, prerequisite chains  | 12, 13, 19, 21                                    |
| **Book-wide**     | Part ordering, curriculum coverage, brand consistency      | 01, 14, 19, 25, 36, 37, 38                        |

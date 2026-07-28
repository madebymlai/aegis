---
title: "Budgeting Convexity - Phase 4 generator-evaluator record"
paper: "Budgeting Convexity"
status: Phase 4 self-scoring - writer_decision=accept
tags:
  - phase4
  - process
---

# Phase 4 generator-evaluator record

Audit trail for the v3.6.6 writer-half contract (`shared/contracts/writer/full.json`) applied to the
[[research/budgeting-convexity/_draft|draft]]. Kept as process evidence, separate from the paper.

## Honest scope of application

- The protocol's load-bearing mechanism is physical call-isolation (Phase 4a never sees the drafting
  artefacts). In a single interactive session that isolation is not literally achievable, so this is
  the protocol's discipline and real acceptance criteria applied, not its call-separation.
- The v3.7.1 / v3.7.3 citation-marker layers, the v3.8 claim-intent manifest, and the Material
  Passport are orchestrated-pipeline machinery the vault flat-file flow does not carry. Citation
  existence/DOI verification is deferred to Phase 5a and the Stage 2.5 integrity gate (level: strict).

## Phase 4a - writer paper-blind pre-commitment

`## Acceptance Criteria Paraphrase` (all seven dimensions, per `pre_commitment_artifacts.
acceptance_criteria_paraphrase.minimum_dimensions = "all"`):

- **D1 section_completeness** - write all six chapters and every subsection from `_outline`, no gap
  placeholders.
- **D2 citation_density** - every factual claim cites a source from `_sources`, or is hedged.
- **D3 argument_blueprint_fidelity** - each section follows the CER chain in `_argument`; no new
  claims or sources beyond the blueprint.
- **D4 total_word_count** - land within +/-10% of 7,500 body words.
- **D5 per_section_word_count** - each chapter within +/-15% of allocation (800 / 1400 / 1200 / 1800 /
  1600 / 700).
- **D6 paragraph_structure** - >=80% of body paragraphs in TEEL; transitions at every chapter
  boundary; intro-first and conclusion-last exempt.
- **D7 register_consistency** - JPM academic register; no colloquial mixing; no em dashes; semicolons
  under 2 per 1000 words; binary-contrast device <=2 prose uses.

[PRE-COMMITMENT-ACKNOWLEDGED]

## Phase 4b - self-scoring

### Round 1 (initial draft v2)

| Dim | Priority | Score | Evidence |
|---|---|---|---|
| D1 section_completeness | mandatory | pass | 6/6 chapters, all subsections, no gaps |
| D2 citation_density | mandatory | pass | every factual claim cited |
| D3 argument_blueprint_fidelity | mandatory | pass | CER chains followed; no new claims |
| D4 total_word_count | high | **warn** | 5,967 body words vs 7,500 (-20.4%), outside +/-10% |
| D5 per_section_word_count | high | **warn** | Ch4 1,149 vs 1,800 (-36%); Ch6 419 vs 700 (-40%) |
| D6 paragraph_structure | normal | pass | TEEL >=80%; transitions present |
| D7 register_consistency | normal | warn | 0 em dashes, 2 semicolons; but "X, not Y" device x7 |

**Failure Condition Checks** - F1 did not fire (no mandatory block); F4 did not fire (no mandatory
warn); F2 did not fire (no high block); **F3 FIRED (sev 40)** - D4 and D5 warn; F0 not selected (F3
outranks).

**Writer Decision Round 1: `revise_in_phase_4b`.**

Revise actions: expanded Ch4 (Floor / Target / Expansion / failure subsections) and Ch6 (contribution,
limits, seats) with TEEL depth using already-cited sources only; topped up Ch2. Softened the
"X, not Y" device from 7 to 2 prose uses (kept the thesis and the sequence/inventory line; 3 remaining
are section headings).

### Round 2 (revised draft, current)

| Dim | Priority | Score | Evidence |
|---|---|---|---|
| D1 section_completeness | mandatory | pass | unchanged; complete |
| D2 citation_density | mandatory | pass | expansions added no uncited claims |
| D3 argument_blueprint_fidelity | mandatory | pass | expansions deepened explanation; Meucci reused, no new source |
| D4 total_word_count | high | **pass** | 6,778 body words vs 7,500 (-9.6%), within +/-10% |
| D5 per_section_word_count | high | **pass** | all sections within +/-15% (Ch1 -14.4 / Ch2 -12.5 / Ch3 -6.3 / Ch4 -9.1 / Ch5 -12.2 / Ch6 +0.3) |
| D6 paragraph_structure | normal | pass | TEEL >=80%; transitions at every boundary |
| D7 register_consistency | normal | pass | 0 em dashes; 2 semicolons (0.3/1000); device 2 prose uses |

**Failure Condition Checks** - F1 / F4 / F2 / F3 all did not fire; **F0 FIRED (sev 10)** - every
mandatory dimension passes.

**Writer Decision Round 2: `accept`.**

## Step 3 Writing Quality Check sweep (measured)

| Check | Limit | Measured | Result |
|---|---|---|---|
| Em dashes | <=3 (house rule 0) | 0 | pass |
| Semicolon density | <=2 / 1000 words | 2 in 6,778 (0.3/1000) | pass |
| Throat-clearing openers | 0 | 0 | pass |
| AI high-frequency terms | avoid | "leverage limits" (literal financial term) only | pass |
| Binary contrast device | <=2 prose | 2 prose (thesis; sequence/inventory) + 3 headings | pass |
| Body word count | 7,500 +/-10% | 6,778 (-9.6%) | pass |

## Outcome

Phase 4 deliverable accepted by the writer half of the contract after one in-phase revision cycle.
Handoff-ready for Stage 2.5 integrity (references/claims verification) then Phase 5a citations /
Phase 5b abstract. The Phase 6 evaluator half (independent scoring) is a separate review layer, run
at the pipeline's Stage 3.

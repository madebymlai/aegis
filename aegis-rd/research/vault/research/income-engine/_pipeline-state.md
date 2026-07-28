---
title: "Convergent Engine - pipeline state"
paper: "The Convergent Income Engine"
tags:
  - pipeline-state
date: 2026-07-25
---

# Pipeline state - income-engine

Orchestrated by `academic-pipeline` v3.19.0. This file is the audit trail; the
`state_tracker_agent` layer is recorded here rather than in memory so a fresh session can
resume without re-deriving intake.

## Intake (Stage 0)

**Entry point:** Stage 1 RESEARCH, scoped to the fold corpus. The vault already holds the
substantive research; the handoff states plainly that it must be cited, not re-derived.

**What the paper is** (`_brief.md`, confirmed by the user at intake): the fold paper on the
convergent seat as a **portfolio role**, consolidating the seven articles the brief says this
paper owns. Title carried from the brief: *The Convergent Income Engine: Funding the Book
Through Ordinary Markets*.

**What the paper is not:** it is not *about* the rent-on-a-balance-sheet synthesis, the
variance-premium correction, the contested intermediary spine, or the §5.5 admission-gate
question. Those are **backbone knowledge** the paper draws on the way a practitioner draws on
prior instinct. They inform the argument and constrain what may be claimed; they are not the
subject.

**Decision recorded at intake:** the article stays **theoretical**. The ΔΘ̂ loader
(`aegis-rd-n77e`) is not a prerequisite and the pipeline does not wait for it. The paper may
name the falsification as an open obligation; it may never imply the test has been run.

> [!important] Superseded 2026-07-25 by the Stage 2.5 gate: the loader landed and the test was run
> The intake premise above is **stale in one respect and still binding in another.** Stale: the loader
> exists (`aegis-rd/scripts/floor_evaluation.py`, committed before `_plan.md` was written) and the test
> has been run, returning ΔΘ̂ = -0.014055, downside correlation +0.2724, all intervals spanning zero,
> `earns_its_seat` False. Any statement that the test cannot be run is out of date. Still binding, and
> now the operative form of the constraint: **never imply more than was found.**
>
> The article remains **theoretical**, and the result does not change that. Under D4 a single candidate's
> measurement cannot speak to the role, so this is evidence about the method's reach rather than about
> the paper's subject. See `_plan.md` D8, which fences it to one paragraph in §8 with the Tasche scope
> condition and the smoothing asymmetry attached.

**Materials in hand at intake**

| Path | Role in the paper |
|---|---|
| `research/README.md` | Epistemic constitution. Behaviours not strategies; ex-ante sign before backtest |
| `research/income-engine/_brief.md` | Porting brief, fold list, contested framing, the open §5.5 obligation |
| `runs/what-is-a-strategy.md` | Five-part test. Load-bearing for the central argument |
| `research-legacy/what-makes-a-convergent-sleeve-an-income-engine.md` | Role definition, ΔΘ̂ ranking rule |
| `notes/income-must-accrue-not-be-captured.md` | Statistical-versus-contractual screen, wall taxonomy, wrapper inversion and dilution |
| `notes/the-premium-is-rent-on-a-balance-sheet.md` | Central synthesis, register of unfollowed behaviours |
| `notes/the-payer-did-not-leave-the-supply-arrived.md` | Variance-premium correction, with its own counter-evidence |
| `notes/window-dressing-at-the-regulatory-snapshot.md` | Worked example of a behaviour meeting the standard |
| `notes/accessible-ordinary-market-income-after-an-open-search.md` | 2026-07-17 roster decision |

**Precedent for output shape:** `research/budgeting-convexity/` is a completed pipeline run in
this vault. Same artifact naming applies.

## Stage log

| Stage | Status | Deliverables | Round trips |
|---|---|---|---|
| 0 INTAKE | complete | this file | 1 |
| 1 RESEARCH | complete, awaiting checkpoint | `_synthesis.md`, `_sources.md`, `_buildability.md` | 2 |

### Stage 1 notes

Three agents dispatched in parallel. `source-register` was interrupted mid-task with nothing written
and was resumed from its own transcript; it now writes incrementally for that reason. Two mid-flight
corrections were issued to `fold-synthesis`, both retracting scope I had wrongly granted it (see
"Orchestrator errors" below).

**The synthesis's own theoretical contribution**, which the paper should carry: durability requires the
constrained party to be **both** the natural arbitrageur **and** non-substitutable by arriving capital.
Prohibition supplies both; capital scarcity supplies only the first and therefore yields a cycle rather
than a durable premium. This explains all four of the corpus's data points, in both signs, and it gives
the §5.5 admission gate actual content: ask not only whether a constraint binds, but whether arriving
capital can relax it. It arrives as a byproduct of the fold rather than as the paper's subject, which
is the scoping the user set at intake.

### Orchestrator errors, recorded

1. I read a tension into ① §4.1 over its identification of the seat with carry, and pre-authorised the
   paper to "refine" ①. Wrong: ① §2.2 already defines the short pole by the binding intermediary
   constraint and never identifies it with carry as a mechanism. Our thesis agrees with ①. Retracted.
2. I claimed §4.1 overstates the Floor's self-sufficiency in fast volatility spikes. Wrong: ① §4.2
   assigns the fast segment to the Target tier by design. Retracted, and the obligation narrowed to a
   candidate-ranking discipline.

Both errors ran the same direction, casting the seat paper as ①'s corrective. A standing constraint is
now in force: treat ① as correct and complete within its scope, check whether an apparent conflict is
already handled in an unread section, and report rather than resolve.

## Standing constraints carried into every stage

1. **Vault conventions** (`research-fin`): kebab-case filenames, **never em dashes**,
   `[[wikilinks]]` internally, minimal frontmatter. The article ends in the strategy hypotheses
   the topic seeds.
2. **Verify load-bearing numbers in the source.** A sub-agent on this desk attributed invented
   figures to a real paper; a separate search surfaced a probably-synthetic article. Anything
   post-2023 needs a venue check.
3. **Do not screen research by implementation.** Topics to articles to hypotheses inferred
   downstream. Filtering upstream by account constraints is the trap that cost this desk a day.
4. **Parallel searches of one corpus are one sample.** Agreement across sub-agents is shared
   selection, not robustness. Primary documents are the corrective.
5. **No claim that the ΔΘ̂ test has been run.** `evaluate_allocator_contribution` is committed
   and tested but cannot be fed (`aegis-rd-n77e`). The paper may pre-register the test; it may
   not imply a result.

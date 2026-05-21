---
date: 2026-05-21
topic: run-lane-vbt-rolling-splitter
---

# Run-Lane VBT Rolling Splitter

## Summary

Add run-lane out-of-sample candidate selection using VBT-native splitter method IDs and params, with `from_rolling` as the first documented example. The goal is to keep the current leaderboard-style research flow while making candidate promotion depend on split-based OOS evidence rather than full-period historical winners.

---

## Problem Frame

`aerd run` currently answers whether configured strategy candidates worked over the configured historical sample under VBT portfolio assumptions. That is useful for exploration, but it does not answer the stronger deployment question: if the system had selected or evaluated strategy and indicator parameters using only past data, would those choices have worked next?

The project is moving toward run-lane strategy research as the primary path, while the existing label/model train lane is legacy context and should not drive new split design. The split contract should follow the project's VectorBT-first pattern: use VBT-native method names and dynamically discovered method params instead of inventing Aegis-specific aliases.

---

## Actors

- A1. Research user: Runs candidate sweeps and needs leaderboard evidence that separates in-sample selection from out-of-sample performance.
- A2. Planning or review agent: Uses the requirements and artifacts to plan implementation and verify that selection semantics are not invented downstream.
- A3. Aegis run lane: Orchestrates candidate generation or fixed-candidate normalization, VBT portfolio simulation, split evidence, and leaderboard reporting.

---

## Key Flows

- F1. Rolling candidate-set selection and evaluation
  - **Trigger:** A run-lane config includes a top-level split selecting a VBT splitter method such as `from_rolling` or `from_purged_kfold` plus method params.
  - **Actors:** A1, A3
  - **Steps:** The run lane builds or normalizes the candidate set, creates VBT split sets, ranks candidates using only the selected in-split set, evaluates selected candidate output on the held-out split set, and aggregates the split evidence into a leaderboard-like result.
  - **Outcome:** The run result shows which candidates survived rolling OOS evaluation and why, without using test-window performance to choose candidates inside that split.
  - **Covered by:** R1, R2, R5, R6, R7

- F2. VBT splitter catalog selection
  - **Trigger:** A user or config asks for a splitter by ID.
  - **Actors:** A1, A3
  - **Steps:** Aegis discovers VBT splitter method names and signatures, exposes method params through `aerd show splitters <method>`, validates authored params against the method signature and generic safety guards, calls the VBT method, and records the selected VBT splitter identity in run evidence.
  - **Outcome:** Configs use exact VBT splitter names and params while Aegis owns validation, evidence, and leaderboard aggregation.
  - **Covered by:** R3, R4, R8, R9

---

## Requirements

**Run-lane rolling selection**
- R1. Run-lane configs must support a top-level split selection for strategy runs, independent of the current train lane.
- R2. Run-lane split support must call VBT splitter constructor classmethods dynamically from config; current VBT splitter constructors are named `from_*`, so methods such as `from_rolling`, `from_purged_kfold`, and later compatible VBT splitter constructors can work through the same pipeline when their required params are supplied.
- R3. Splitter method IDs in config and evidence must preserve exact VBT constructor naming, for example `split.method: from_rolling`, rather than Aegis-specific aliases such as `walk_forward`; method-required or intentionally overridden VBT kwargs belong under `split.params`, omitted optional kwargs use VBT defaults, and Aegis guard fields stay outside `params`.
- R4. Aegis must discover VBT splitter method names and method params dynamically for catalog and validation purposes, expose them through a CLI such as `aerd show splitters <method>`, and use generic safety guards for params Aegis cannot safely pass through.
- R5. Rolling run mode must evaluate candidate sets, not standalone indicators, as the primary promotion unit; playbook sweeps produce many composed strategy x indicator candidates, while fixed component runs are the same shape with one fixed candidate.
- R6. Within each rolling split, candidate selection must use only the selection window and must not use the subsequent test window to choose that split's candidate winners.
- R7. The leaderboard-like output must rank OOS test-window evidence and must clearly distinguish it from full-period historical ranking.
- R8. Run evidence must record the native VBT splitter identity and enough public split membership or bounds evidence for review without requiring private native object inspection.
- R9. User-facing language for run-lane rolling splits should call the in-sample portion a selection or optimization window, not ML training, to avoid confusion with the legacy train lane.

**Leaderboard and artifacts**
- R10. The rolling output must preserve the current run-lane habit of returning one concise final leaderboard, while adding per-split diagnostics that explain each roll's selection, OOS performance, selection count, and stability; this does not require a separate user-facing leaderboard artifact for every roll.
- R11. A candidate selected in only a small number of rolling splits must not appear equivalent to a candidate selected repeatedly unless that difference is visible in the leaderboard or diagnostics.
- R12. The run result must preserve failure and partial-success evidence when some candidates or split windows cannot be evaluated.

**Train lane boundary**
- R13. This feature must not add new train-lane support, rework train-lane split semantics, or design run-lane splitter abstractions around preserving label/model ML side support.
- R14. Removing the train lane, train split config, labelers, model plugins, and `--train` flag is the intended near-term follow-up; reviews should not treat preserving that side support as a requirement for this rolling run-lane work.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R5.** Given a run-lane config selecting VBT splitter method `from_rolling`, when `aerd run` executes, it evaluates the run's candidate set through rolling selection/test windows, whether that set is a multi-candidate playbook sweep or a fixed component run with one candidate, and produces a run-lane result rather than invoking the train lane.
- AE2. **Covers R6, R7.** Given a rolling split with a past selection window and a future test window, when candidates are ranked for that split, the chosen candidate is determined only from the selection window and the reported OOS value comes from the following test window.
- AE3. **Covers R4, R8.** Given VBT exposes multiple splitter constructors, when Aegis builds its splitter catalog, discovered names and signature-derived params are visible through `aerd show splitters`, params are validated dynamically, and the selected splitter identity is recorded in public run evidence.
- AE4. **Covers R10, R11.** Given candidate A is selected in one split and candidate B is selected in six splits, when the final rolling leaderboard and per-split diagnostics are inspected, the output makes the different selection coverage visible alongside OOS metrics without requiring a separate leaderboard artifact per roll.
- AE5. **Covers R12.** Given one split fails during portfolio simulation for a subset of candidates, when the run finishes or fails, the artifact evidence shows which split/candidate evaluations succeeded, failed, or were excluded.
- AE6. **Covers R13, R14.** Given the current train lane still exists, when rolling run-lane splitter support is added, train-lane behavior is not expanded, and near-term train-lane removal remains the intended follow-up rather than a reason to preserve ML side support.

---

## Success Criteria

- Research users can distinguish a full-period historical winner from a rolling OOS survivor without reading implementation details.
- A run-lane rolling result can support candidate promotion decisions with clearer OOS evidence than the current full-period leaderboard.
- Config and evidence use VBT-native splitter names consistently enough that users can map Aegis behavior back to VBT documentation.
- A downstream planning agent can implement the feature without inventing whether rolling selection uses the run's candidate set, exact VBT IDs, or train-lane semantics.

---

## Scope Boundaries

- Train-lane removal is deferred from this rolling OOS feature only as a sequencing boundary; removing the train split config, labelers, model plugins, train-lane logic, and `--train` flag is the intended near-term follow-up.
- Directional ML labels, supervised model training, and probability-to-signal behavior are out of scope for this feature.
- RL, contextual bandits, and live allocation policy learning are out of scope.
- NautilusTrader runtime execution and paper-trading validation are out of scope.
- Indicator-only diagnostics can remain possible diagnostics, but the primary v1 promotion unit is the run candidate: a composed playbook candidate for sweeps, or the single fixed candidate for component runs.
- Blindly passing unsafe or internal VBT kwargs is out of scope; dynamic discovery should still deny params Aegis cannot safely expose.
- `from_purged_kfold` and other VBT splitters are still splitters and should use the same run-lane scoring pipeline when VBT can build their split sets from config. `from_rolling` remains the easiest chronological OOS example, not a hard-coded special route.

---

## Key Decisions

- Use VBT exact splitter IDs: This follows the existing VectorBT-first style used for providers and metrics and avoids Aegis-specific aliases.
- Use VBT method names dynamically: `from_rolling` is the clearest chronological OOS example, but the run lane should not hard-code a separate implementation route for it when other VBT splitters can produce usable split sets.
- Keep the output leaderboard-like: The existing run-lane UX is already oriented around candidate leaderboards, so rolling OOS should strengthen that output rather than introduce a separate reporting mental model.
- Treat train-lane removal as a near follow-up: The immediate change should improve run-lane OOS evidence without expanding ML side support, and the separate removal work should delete the train split, labeler/model plugin, and `--train` surfaces rather than preserve them.

---

## Dependencies / Assumptions

- VBT splitter constructors remain available with stable method names such as `from_rolling`.
- The current run lane can continue to centralize portfolio simulation and metrics so neither playbooks nor components own their own metric source.
- Dynamic splitter invocation should prioritize clarity and auditability without forcing Aegis to maintain static param lists for every VBT method.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R4][Technical] What exact shape should `aerd show splitters <method>` return for human and JSON output?
- [Affects R7, R10][Technical] Should the primary split metric aggregate held-out windows as one stitched portfolio result, a weighted mean of split metrics, or both with one designated as primary?
- [Affects R4][Technical] Which VBT kwargs should Aegis deny or reserve because they are unsafe, internal, or require non-config runtime context?

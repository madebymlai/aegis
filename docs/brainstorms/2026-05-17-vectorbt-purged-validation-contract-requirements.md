---
date: 2026-05-17
topic: vectorbt-purged-validation-contract
github_issue: 3
---

# VectorBT Purged Validation Contract

## Summary

Issue #3 will turn the label split-safety contract from #2 into decision-grade validation. It will define one VectorBT-backed purged-CV path for look-ahead supervised labels, covering `FIXLB`, `TRENDLB`, and `PIVOTLB` only when prediction and evaluation windows are concrete enough to prove leakage was purged.

---

## Problem Frame

`research/aegis_research/splits.py` and `research/aegis_research/validation.py` define the evidence contract for out-of-sample metrics. The current split pipeline included chronological holdout and VectorBT rolling windows, but look-ahead supervised targets from `research/aegis_research/labels.py` require purged validation rather than a temporary unpurged diagnostic state.

The follow-up comment on issue #3 says the intent plainly: after #2, consume label target availability, look-ahead, and evaluation-window metadata; provide one solid purged-CV path for look-ahead labels; and replace the temporary unpurged/non-decision-grade state rather than keeping long-lived parallel validation branches. Source: https://github.com/madebymlai/aegis-rd/issues/3#issuecomment-4470615366.

This matters because VectorBT purged CV is interval-based. It needs prediction times and evaluation times for samples, then removes train samples whose intervals overlap test samples and applies embargo after test evaluation times. Fixed `embargo_bars` trimming at the beginning of a test set is not equivalent evidence of leakage removal.

---

## Actors

- A1. Experiment author: Chooses label target and validation mode in experiment config.
- A2. Label target stage: Emits selected target values plus target availability, look-ahead, and evaluation-time metadata.
- A3. Split construction stage: Converts the target safety contract into train/test memberships and split metadata.
- A4. Validation stage: Trains, predicts, simulates, and reports metrics per split and set.
- A5. Reviewer or automation agent: Decides whether validation artifacts are decision-grade and reproducible.

---

## Key Flows

- F1. Build a decision-grade purged split
  - **Trigger:** A look-ahead supervised target is selected and validation metrics are requested.
  - **Actors:** A1, A2, A3, A5
  - **Steps:** Read target availability metadata, derive concrete prediction and evaluation times, exclude unavailable rows, construct purged train/test memberships, and record purging and embargo assumptions.
  - **Outcome:** The split artifact proves which samples were eligible for training and testing after leakage controls.
  - **Covered by:** R1, R2, R3, R4, R5, R10, R11, R19
- F2. Validate with split/set identity preserved
  - **Trigger:** One or more purged validation splits are available.
  - **Actors:** A3, A4, A5
  - **Steps:** Train on each purged train membership, produce test outputs and optional train diagnostics with explicit set identity, simulate train/test evidence separately, and aggregate only traceable split outputs.
  - **Outcome:** Metrics, probabilities, entries, exits, and portfolios can be traced to the split and set that produced them.
  - **Covered by:** R6, R7, R8, R9, R13, R14, R15, R16
- F3. Fail closed when safety cannot be proven
  - **Trigger:** Target metadata, index structure, or post-purge membership makes leakage-safe validation uncertain.
  - **Actors:** A2, A3, A4, A5
  - **Steps:** Detect missing or unknown evaluation windows, unsupported index/time assumptions, empty splits, too few samples, or too few target classes before training or reporting decision-grade metrics.
  - **Outcome:** The run stops with visible diagnostics instead of producing misleading validation artifacts.
  - **Covered by:** R5, R11, R12, R15, R16, R17, R19

---

## VBT Evidence Used

| Evidence | Confirmed behavior or guidance | Requirement impact |
|---|---|---|
| VectorBT API, `Splitter.from_purged_kfold`: https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter.from_purged_kfold | Accepts `n_folds`, `n_test_folds`, `purge_td`, `embargo_td`, `pred_times`, and `eval_times`, and returns a `Splitter`. | Purged validation should use explicit prediction and evaluation times, not only bar trimming. |
| VectorBT API, `PurgedKFoldCV`: https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/purged/#vectorbtpro.generic.splitting.purged.PurgedKFoldCV | Samples are tagged with prediction and evaluation times; overlapping train/test intervals are dropped; embargo enforces a gap after test evaluation times. | Decision-grade look-ahead validation requires interval metadata and proof that purging was applied. |
| VectorBT Cross-validation Applications, "Column stacking": https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/applications/#column-stacking | `Splitter.take` can slice array-like and VectorBT objects, stack by split/set, and attach index bounds with `attach_bounds="index"` and `right_inclusive=True`. | Split artifacts should preserve set labels, sliced memberships, and audit-friendly bounds where safe. |
| VectorBT Cross-validation Splitter, "Bounds": https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/splitter/#bounds | Bounds can be integer or datetime; starts are inclusive and ends are exclusive unless `right_inclusive=True`. | Bounds should be recorded explicitly and interpreted consistently. |
| VectorBT Cross-validation Splitter, "Scikit-learn": https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/splitter/#scikit-learn | Time series has temporal dependency; test periods should follow training periods to avoid future data predicting the past. | Generic shuffled or unordered CV is not acceptable for decision-grade trading validation. |
| VectorBT Cookbook, "Splitting": https://vectorbt.pro/pvt_16ebf9ef/cookbook/cross-validation/#splitting | `from_n_rolling(length="optimize", optimize_anchor_set=1)` can pick longest windows with non-overlapping test ranges. | Rolling validation can be useful generally, but it is not the schema v2 validation path for look-ahead labels. |
| Discord support thread on `TRENDLB`: https://discord.com/channels/918629562441695344/918630948248125512/1104404155361153054 | Maintainer says `TRENDLB` is future-looking, used for ML training, and not appropriate as a non-look-ahead indicator input; `PIVOTINFO` confirmed/running outputs are different. | Label functions may be valid targets, but split construction must account for future evaluation windows. |
| Discord support thread on purged splitter bounds: https://discord.com/channels/918629562441695344/918630948248125512/1318927881740746833 | Purged ranges can have gaps and bounds calls can hit `ValueError: Range is not constant`; maintainer suggested `check_constant=False`. | Exact membership must be authoritative; bounds are audit metadata, not the only proof. |
| Discord support thread on `PurgedKFoldCV` fold control: https://discord.com/channels/918629562441695344/918630948248125512/1256246675924717670 | Maintainer says `cv_split` does not support selecting specific purged test folds for every aggregation shape; build a splitter and handle it manually when needed. | Aegis should own its split/set artifact contract around VBT splitters instead of hiding behind decorator behavior. |

No direct docs-vs-support contradiction was found. The only tension is that VectorBT tutorials show `TRENDLB` in ML examples without presenting those examples as purged, while the purged-CV API and support guidance make future-looking target safety explicit. For Aegis decision-grade metrics, prefer the stricter documented purged-CV behavior.

---

## Requirements

**Purged CV Contract**
- R1. `purged_kfold` must be the decision-grade validation path for supervised look-ahead label targets.
- R2. A purged split must be built from concrete prediction times and evaluation times for the selected target samples.
- R3. Fixed test-bar trimming must not be treated as equivalent to VectorBT interval purging.
- R4. Label horizon belongs in evaluation times; `purge_td` and `embargo_td` are additional buffer settings that must be recorded separately.
- R5. `FIXLB`, `TRENDLB`, and `PIVOTLB` may all participate in decision-grade validation only when exact per-row evaluation times can be produced; otherwise the run must fail before decision-grade metrics are produced.

**Split Artifacts And Metadata**
- R6. Purged validation must expose one split artifact contract with split labels, set labels, train/test membership, lengths, dropped rows, source-index identity, bounds where available, and purging or embargo assumptions.
- R7. Exact train/test membership must be the authoritative split evidence, especially for gapped purged ranges.
- R8. Integer and timestamp bounds must be exported when they can be computed safely; if purged ranges are non-constant or gapped, metadata must preserve the failure/fallback while keeping exact membership.
- R9. Probability, entry, exit, metric, and portfolio artifacts must preserve unambiguous split and set identity rather than flattening everything into plain split labels.

**Label Metadata And Availability**
- R10. Split construction must consume #2 label target availability, look-ahead, and evaluation-window metadata instead of reverse-engineering label semantics from target values.
- R11. Rows with unavailable target evaluation windows must be excluded before split construction and counted with a reason.
- R12. Multi-symbol or multi-target evaluation-time differences must be handled by an explicit conservative policy, such as latest evaluation time per timestamp, or rejected; silent first-column selection is not allowed.

**Validation Behavior**
- R13. Models must train only on the purged train membership and decision-grade metrics must come only from test membership.
- R14. Train diagnostics may be produced, but they must remain separate from test evidence and must not imply a deployable top-level model.
- R15. Empty train/test sets, too few samples, or too few target classes after purging and embargoing must fail before model training.
- R16. Validation metadata may mark outputs as decision-grade only when purging was applied, exact intervals were recorded, and target/model compatibility passed.

**Rolling, Holdout, And Index Constraints**
- R17. Holdout and rolling validation must not be exposed by the schema v2 experiment contract for current look-ahead label generators.
- R18. Rolling split metadata must record resolved window length, frequency assumptions, `length="optimize"` use, test anchoring, set labels, and effective train/test bounds.
- R19. Datetime indexes should use time-based purging and embargo metadata; non-datetime or synthetic range indexes must provide an explicit mapping to prediction and evaluation times or fail closed.

**Evidence And Documentation**
- R20. The issue #3 implementation notes and user-facing docs must answer the best-practice decisions from the issue: purged split contract, VectorBT splitter use, label look-ahead handoff, validation artifact identity, and failure conditions.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R4, R11, R16.** Given a `FIXLB(n=5)` supervised target, when `purged_kfold` validation runs on a datetime index, evaluation times reflect the five-bar target horizon, unavailable tail rows are excluded, purging metadata is recorded, and test metrics may be marked decision-grade.
- AE2. **Covers R5, R10, R15, R16.** Given a `TRENDLB` target whose metadata still says `variable_unknown`, when decision-grade validation is requested, the run fails before model training instead of producing unpurged metrics.
- AE3. **Covers R5, R10, R12.** Given a `PIVOTLB` target with exact per-row pivot resolution times, when multiple target columns have different evaluation times for the same timestamp, the split contract applies a declared conservative row-level policy or rejects the run visibly.
- AE4. **Covers R6, R7, R8.** Given a purged split with gapped ranges where bounds are not constant, when artifacts are written, exact membership is preserved and bounds metadata records the safe fallback rather than dropping split evidence.
- AE5. **Covers R3, R13, R14, R17.** Given a config with `split.kind: rolling` or `split.kind: holdout`, validation fails before artifacts are written because schema v2 supports only purged look-ahead validation.
- AE6. **Covers R15.** Given a purged train set with only one target class after leakage controls, when validation reaches the model boundary, the run fails with split/model compatibility diagnostics before fitting.

---

## Success Criteria

- Experiment authors can run look-ahead label validation only through a path that proves purging was applied or fails before misleading metrics are produced.
- Reviewers can inspect artifacts and understand prediction times, evaluation times, purging settings, embargo settings, split membership, set identity, and metric trust level without loading private native objects.
- The temporary #2 state of `purging_required: true` and `purging_applied: false` is replaced for supported decision-grade runs.
- `FIXLB`, `TRENDLB`, and `PIVOTLB` are all addressed by the contract, with exact evaluation-time requirements rather than silent assumptions.
- Planning can proceed without inventing product behavior for split trust, artifact identity, failure modes, or best-practice answers.

---

## Scope Boundaries

- Do not implement new estimator families, regression support, multiclass support, or probability semantics in #3; those belong to model-target work such as #9.
- Do not implement new trading-signal conversion semantics in #3; signal behavior belongs to downstream signal work such as #11.
- Do not build a custom cross-validation engine that competes with VectorBT unless planning finds a specific VBT limitation that blocks the confirmed contract.
- Do not preserve long-lived parallel unpurged validation branches for look-ahead labels.
- Do not treat VectorBT label generators as predictor features in this issue.
- Do not claim all label configurations are decision-grade merely because the label kind is supported; exact evaluation windows are still required.

---

## Key Decisions

- One safe path: #3 should add one decision-grade purged-CV contract rather than keep holdout, rolling, and purged paths as equally trusted options for look-ahead labels.
- All labels now, with proof: `FIXLB`, `TRENDLB`, and `PIVOTLB` are in scope, but unknown evaluation windows fail closed instead of being guessed.
- Evaluation times over bar trimming: target look-ahead must be represented as prediction/evaluation intervals, while `purge_td` and `embargo_td` are recorded safety buffers.
- Exact membership over bounds: bounds are useful audit evidence, but purged ranges can be gapped, so membership is the source of truth.
- VectorBT-first: use VBT splitters and documented behavior as the baseline; project recommendations should be labeled as recommendations when VBT docs do not specify policy.

---

## Dependencies / Assumptions

- Issue #2 has landed enough target contract metadata for `FIXLB` fixed horizons and a conservative `variable_unknown` state for `TRENDLB` and `PIVOTLB`.
- Issue #3 may make targeted changes to `research/aegis_research/labels.py` if exact evaluation times are required to make `TRENDLB` or `PIVOTLB` decision-grade.
- `research/aegis_research/splits.py` remains the split construction boundary and `research/aegis_research/validation.py` remains the validation execution boundary.
- `docs/vectorbt-scaffold.md` currently documents diagnostic validation for unpurged look-ahead labels and should be updated when #3 replaces that state with purged validation.
- VectorBT PRO behavior cited here is from the available docs/API/support evidence as of 2026-05-17.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R5, R10][Needs research] What exact per-row evaluation-time derivation is correct for `TRENDLB` and `PIVOTLB` using VectorBT native outputs and source behavior?
- [Affects R1, R4, R19][Technical] What config names and validation bounds should represent `purged_kfold`, `n_folds`, `n_test_folds`, `purge_td`, `embargo_td`, and index-time assumptions?
- [Affects R6, R8, R9, R16][Technical] What artifact schema version should carry split membership, bounds fallback metadata, set identity, and decision-grade trust fields?
- [Affects R17, R20][Technical] What migration or documentation update should remove examples that imply unpurged look-ahead validation is acceptable?

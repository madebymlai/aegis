---
date: 2026-05-17
topic: vectorbt-label-contract
---

# VectorBT Label Contract

## Summary

Make label generation VectorBT-first and target-contract-driven: preserve native label-generator objects and raw label semantics, derive explicit model-ready targets only as named transforms, and expose enough lineage, diagnostics, and look-ahead metadata for models, splitters, and reviewers to make safe downstream decisions.

---

## Problem Frame

`research/aegis_research/labels.py` defines the supervised target contract for the research loop. The current implementation calls VectorBT PRO label generators, but it collapses different label families into one binary panel too early. `FIXLB` future returns, `TRENDLB` trend modes, and `PIVOTLB` sparse pivot events carry different meanings, leakage assumptions, class distributions, and model compatibility constraints.

This matters because labels decide what the model is trying to learn. If the label boundary hides native values, parameter identity, target transforms, sparse-event semantics, or look-ahead windows before artifacts are recorded, downstream validation and model metrics can look rigorous while training against the wrong target or evaluating leaked samples.

The labeler is also harder than indicators because label generation intentionally uses future information for targets. VectorBT docs warn label functions may introduce look-ahead bias and should be used only for target variables, not predictor variables. Discord support context reinforces that `TRENDLB`/`PIVOTLB` style labels are look-ahead outputs, while `PIVOTINFO` has separate confirmed/running outputs that can be safer for feature or regime use when chosen carefully. The project needs a label contract that makes those distinctions impossible to miss.

---

## Actors

- A1. Experiment author: Selects label generator, parameters, and target transform in experiment config.
- A2. Experiment runner: Builds labels, records artifacts, and must fail visibly on incompatible target/model/split assumptions.
- A3. Model training stage: Consumes a typed model-ready target panel without needing to infer VectorBT label semantics.
- A4. Validation split stage: Needs label look-ahead and evaluation-time metadata to prevent leakage.
- A5. Run reviewer or automation agent: Inspects artifacts to understand native labels, derived targets, class balance, target type, and leakage assumptions.

---

## Key Flows

- F1. Build native label generator output
  - **Trigger:** A validated experiment config requests `FIXLB`, `TRENDLB`, or `PIVOTLB` labels for one or more symbols and parameters.
  - **Actors:** A1, A2, A5
  - **Steps:** Validate label kind and params, run the VectorBT label generator with visible parameter levels, preserve the native object and raw `.labels`, normalize symbol/parameter lineage, and record native distributions and missing values.
  - **Outcome:** Native label semantics remain inspectable before any model-facing conversion.
  - **Covered by:** R1, R2, R3, R4, R5, R15, R17
- F2. Derive a typed model target
  - **Trigger:** Native labels are available and a model stage needs a supervised response.
  - **Actors:** A1, A2, A3, A5
  - **Steps:** Apply a named target transform appropriate to the label kind and mode, classify the target as binary, continuous, sparse event, or regime, record transform lineage and distributions, and reject incompatible assumptions early.
  - **Outcome:** Models receive a target contract, not an arbitrary binary DataFrame.
  - **Covered by:** R6, R7, R8, R9, R10, R11, R12, R13
- F3. Hand labels to modeling and validation boundaries
  - **Trigger:** Feature, label, and split construction are about to intersect.
  - **Actors:** A2, A3, A4, A5
  - **Steps:** Align feature and target panels, expose dropped rows and unavailable label windows, pass look-ahead/evaluation-time metadata to split planning, and fail fast when current model or signal stages cannot consume the target type.
  - **Outcome:** Downstream work can be planned from explicit contracts instead of hidden label assumptions.
  - **Covered by:** R14, R16, R18, R19, R20

---

## Research Findings

- VectorBT `FIXLB`, `TRENDLB`, and `PIVOTLB` are `IndicatorBase`-style objects with `input_names`, `param_names`, `output_names`, `.labels`, stats/plots, `.run(...)`, and `run_combs`.
- VectorBT docs say ordinary parameter sweeps should pass parameter lists to `.run(...)`; `run_combs` is for multiple indicator instances.
- VectorBT docs say `hide_params=True` hides parameter levels; `hide_params=None` and `hide_default=False` preserve visible params and defaults in outputs.
- `FIXLB` is a look-ahead fixed label generator. Its native labels are future percentage changes, not binary classes.
- `TRENDLB` exposes `TrendLabelMode`: `Binary`, `BinaryCont`, `BinaryContSat`, `PctChange`, and `PctChangeNorm`. Only `Binary` is naturally a binary classifier target.
- `PIVOTLB` emits pivot labels based on `Pivot`: `Valley=-1`, `Peak=1`, with non-pivot rows as `0`; this is a sparse event/regime target, not a dense balanced class target by default.
- VectorBT label Numba docs warn not to use label functions for predictor variables because they may introduce look-ahead bias; they should be used only for targets.
- VectorBT purged CV docs require prediction times and evaluation times for samples; overlapping prediction/evaluation intervals should be purged, with embargo applied after test evaluation times.
- Discord support distinguishes look-ahead trend/pivot labels from `PIVOTINFO` outputs such as `conf_pivot`, `conf_value`, `last_pivot`, and `last_value`; `pivots` and `modes` are for plotting/look-ahead contexts and should not be silently treated as safe model inputs.

---

## Requirements

**Native Label Contract**
- R1. Label generation must preserve the native VectorBT label-generator object when a target is produced by `FIXLB`, `TRENDLB`, or `PIVOTLB`.
- R2. Native `.labels` output must be retained separately from any derived model-ready target.
- R3. Label outputs must preserve visible parameter levels by default; hiding all params must not be the artifact or target-boundary default.
- R4. Label parameter sweeps must use VectorBT `.run(...)` parameter-list semantics where appropriate and reserve `run_combs` for multiple-generator-instance cases.
- R5. Multi-symbol and single-symbol label outputs must preserve stable symbol identity without silently selecting the first column.

**Target Derivation And Typing**
- R6. Binary conversion must be an explicit named target transform, not embedded inside native label generation.
- R7. Each derived target must declare a target kind: binary classification, regression/continuous, sparse event, or regime label.
- R8. Target transform lineage must record source generator, source output, params, symbol, transform name, thresholds or positive class, and native-to-derived value mapping.
- R9. Native and derived distributions must both be reported, including class counts, value summaries, sparse-event frequency, NaN counts, and dropped rows.
- R10. Current model compatibility must be explicit: unsupported target kinds must fail fast or produce a typed incompatibility signal before training.

**Label-Kind Semantics**
- R11. `FIXLB` must expose native future-return labels and treat thresholding as a target transform over those returns.
- R12. `TRENDLB` `mode="binary"` may derive a binary class target without remapping beyond explicit positive-class metadata.
- R13. `TRENDLB` continuous and percentage-change modes must be typed as continuous targets unless an explicit, documented transform converts them to a classifier target.
- R14. `TRENDLB` binary labels must also be eligible as regime labels for split/group analysis, separate from supervised model targets.
- R15. `PIVOTLB` must preserve native `Valley=-1`, non-pivot `0`, and `Peak=1` semantics and treat valley/peak prediction as sparse event targeting with mandatory imbalance diagnostics.

**Look-Ahead, Alignment, And Split Handoff**
- R16. Label artifacts must expose look-ahead assumptions and evaluation-window metadata sufficient for #3 to build purged or embargoed validation splits.
- R17. Boundary rows made unavailable by fixed horizons, future pivots, trend confirmation, or missing OHLC data must be counted and excluded through an explicit policy.
- R18. Feature-target alignment must be verified after invalid-value handling and before split construction or training.
- R19. Label-generator outputs that are safe only for targets must not be accepted as model features without an explicit future feature/regime contract.

**Artifacts, Config, And Tests**
- R20. Public artifacts must include portable label metadata, target schema, transform lineage, diagnostics, and native-artifact sidecar metadata without absolute paths or secrets.
- R21. Config validation must reject unknown label kinds, unsupported modes, invalid enum values, unsafe implicit target transforms, and inconsistent parameter-grid semantics before label-dependent side effects.
- R22. Tests must verify native VectorBT semantics and lineage for multiple symbols, visible params, `FIXLB` future returns, `TRENDLB` mode typing, `PIVOTLB` sparse events, invalid-mode failures, and model-compatibility failures.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R4, R11.** Given `FIXLB` with horizons `[1, 5]`, when labels are built, one native VectorBT output preserves visible `n` identity, native labels remain future returns, and any binary target records threshold lineage separately.
- AE2. **Covers R7, R12, R13.** Given `TRENDLB(mode="binary")`, when targets are derived, the target kind is binary classification; given `TRENDLB(mode="pct_change")`, the target kind is continuous unless config explicitly requests a supported classifier transform.
- AE3. **Covers R14, R16.** Given `TRENDLB(mode="binary")` used for regime analysis, when artifacts are inspected, the regime role is separate from supervised target role and look-ahead metadata is available for split planning.
- AE4. **Covers R9, R15.** Given `PIVOTLB` with `positive_value=-1`, when targets are derived, native `Valley=-1`, `0`, and `Peak=1` distribution is recorded and the derived valley-event target reports sparse-event frequency and imbalance.
- AE5. **Covers R5, R18.** Given multi-symbol labels and features, when the model boundary is reached, symbols must match exactly or the run fails before training.
- AE6. **Covers R10, R13.** Given a continuous target and the current logistic-regression-only model, when training is requested, the run fails with a target/model incompatibility diagnostic rather than silently binarizing or pretending predictions are probabilities.
- AE7. **Covers R16, R17.** Given `FIXLB(n=5)`, when split metadata is prepared, the final five rows are unavailable for target evaluation and the target contract exposes evaluation-time assumptions for purged CV work in #3.
- AE8. **Covers R19.** Given a config that attempts to use `TRENDLB` native labels as model features, when validation runs, it fails or requires a separate explicit feature/regime contract because label functions are look-ahead target generators.

---

## Success Criteria

- Experiment authors can choose `FIXLB`, `TRENDLB`, or `PIVOTLB` without losing native label semantics or accidentally forcing every target into binary classification.
- Model training receives an explicit target contract with compatibility metadata rather than an untyped label DataFrame.
- Validation planning can see label look-ahead and evaluation-time assumptions before metrics are considered reliable.
- Run reviewers can reconstruct native label values, derived target values, parameter identity, symbol identity, target kind, and transform logic from artifacts.
- Downstream planning for #3, #9, and #11 can proceed without inventing what the label stage means.

---

## Scope Boundaries

- Do not implement regression estimators, multiclass classifiers, or event-model families in #2; model-family support belongs to #9.
- Do not implement trading-signal conversion for non-probability predictions in #2; signal semantics belong to #11.
- Do not implement the full purged CV engine in #2; split construction belongs to #3, using metadata emitted by this label contract.
- Do not treat `PIVOTINFO` as part of the supervised label-generator contract in v1; it is relevant context for future safe feature/regime work because confirmed/running pivot outputs differ from look-ahead labels.
- Do not use VectorBT label functions as predictor variables in this issue.
- Do not add backward-compatibility shims for the current lossy binary-only label contract unless a concrete persisted artifact or external consumer requires it.
- Do not hide native objects behind portable metadata only; private native persistence remains valuable when object state affects reproducibility.

---

## Key Decisions

- Native-first label boundary: VectorBT label-generator objects and raw `.labels` remain authoritative until target derivation.
- Typed target boundary: Models consume a model-ready target plus metadata, not native labels directly.
- Binary is one target transform, not the label contract: `FIXLB` and `PIVOTLB` must not be treated as inherently binary just because the current baseline model is binary.
- `TRENDLB` has two roles: supervised target source and regime-analysis source. These roles must be explicit in metadata and config.
- `PIVOTLB` is sparse event semantics by default. Valley/peak prediction must carry event imbalance diagnostics and positive-event meaning.
- Look-ahead is expected for targets but must be explicit. It becomes a validation concern through #3, not a hidden property of `labels.py`.
- `PIVOTINFO` belongs in the conversation but not this target contract. Its confirmed/running outputs are candidates for future non-look-ahead features or regimes, while its `pivots` and `modes` remain unsafe for predictive features without explicit handling.

---

## Dependencies / Assumptions

- Issue #5 defines the matching native-first indicator and model-feature boundary that this label contract should align with.
- Issue #3 must consume label look-ahead/evaluation-time metadata to build purged or embargoed validation splits.
- Issue #9 must consume the typed target contract to decide estimator family, probability semantics, class mapping, and unsupported target failures.
- Issue #11 must consume prediction semantics from #9 before converting model outputs into entries and exits.
- `research/aegis_research/labels.py` currently owns label generation and `LabelResult`.
- `research/aegis_research/config.py` currently validates `LabelConfig` and restricts `TRENDLB` to binary mode in schema v1.
- `research/aegis_research/experiments.py` currently passes `label_result.labels` directly into feature alignment, split construction, model training, and validation.
- `research/aegis_research/models.py` currently assumes labels are binary classifier targets and belongs to #9 for broader target consumption.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R8, R20][Technical] What exact target-contract dataclass and artifact schema should represent native output, derived target, transform lineage, and compatibility metadata?
- [Affects R16, R17][Technical] What v1 representation of evaluation time is sufficient for `FIXLB`, `TRENDLB`, and `PIVOTLB` before #3 implements full purged CV?
- [Affects R15][Technical] Should `PIVOTLB` support both binary event targets and multiclass `{-1, 0, 1}` targets in the initial contract, or should multiclass consumption be deferred to #9 while native labels are still preserved?
- [Affects R21][Technical] Should labels reuse the indicator registry/config-spec pattern, or use a smaller label-specific registry with generator-specific transform rules?
- [Affects R20][Technical] Which native label artifacts should be persisted privately in v1, and how should public sidecars summarize object state without leaking non-portable data?

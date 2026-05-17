---
date: 2026-05-17
topic: model-plugin-target-probability-contract
github_issue: 9
---

# Model Plugin Target And Probability Contract

## Summary

Issue #9 will replace hard-coded estimator behavior with a plugin-only model boundary. Core model orchestration will validate #2 typed targets, call a trusted registered model plugin, preserve binary probability meaning through `positive_class_probability`, and support live incremental updates only when a plugin explicitly declares that capability.

---

## Problem Frame

`research/aegis_research/models.py` currently owns too much model meaning directly. It builds a fixed `StandardScaler + LogisticRegression` pipeline, assumes the incoming label panel is already a binary classifier target, pools timestamp-symbol rows into one training table, reads `predict_proba(...)[..., 1]` as `long_probability`, and persists only the fitted pipeline object.

That was useful scaffolding, but it hides decisions that determine research correctness: which target kinds a model can consume, which class is positive, whether probabilities are calibrated, whether model state is a per-validation-split artifact or a live updateable state, and whether artifacts are interpretable later without guessing from code. The issue comments add two important constraints: post-#2 model work should consume the typed target contract rather than native VectorBT label arrays, and v1 does not need per-asset or cross-sectional model-family schematics.

VectorBT PRO evidence reinforces the need for a strict boundary. VBT labelers such as `FIXLB`, `TRENDLB`, and `PIVOTLB` are target generators with different native meanings, not interchangeable binary classes. VBT also treats model outputs as ordinary pandas-compatible arrays that can feed backtesting, so Aegis can own the model plugin contract without requiring VBT itself to own model implementations.

---

## Actors

- A1. Experiment author: Selects a registered model plugin in experiment config.
- A2. Model plugin author: Implements a trusted project-code plugin that satisfies the model contract.
- A3. Experiment runner: Validates target/model compatibility, trains or updates model state, predicts, and records artifacts.
- A4. Validation stage: Needs split-local model outputs and diagnostics that preserve train/test evidence.
- A5. Signal stage: Consumes prediction panels only when prediction semantics are compatible with trading-signal policy.
- A6. Reviewer or automation agent: Inspects artifacts to understand plugin identity, target meaning, probability mapping, diagnostics, and model-state lineage.

---

## Key Flows

- F1. Run a registered batch model plugin
  - **Trigger:** A validated experiment requests a registered model plugin.
  - **Actors:** A1, A2, A3, A4, A6
  - **Steps:** Resolve the plugin id through trusted project registration, validate the #2 target contract against plugin capabilities, fit the plugin on the split-local training data, select positive-class probability by class label, and record plugin/model diagnostics.
  - **Outcome:** The validation split has traceable binary probability outputs and metadata without core owning a specific estimator implementation.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R17, R18, R19, R20
- F2. Update live model state incrementally
  - **Trigger:** An experiment requests live incremental update mode and provides prior model state.
  - **Actors:** A1, A2, A3, A6
  - **Steps:** Load trusted prior state, verify plugin and contract compatibility, reject unsupported or incompatible state, update only with eligible past training data, and write a new model-state artifact with update lineage.
  - **Outcome:** Incremental training is possible for capable plugins without turning every plugin into a live lifecycle model.
  - **Covered by:** R12, R13, R14, R15, R16, R19, R20, R21
- F3. Author and verify a model plugin
  - **Trigger:** A developer wants to add a new model implementation.
  - **Actors:** A2, A3, A6
  - **Steps:** Follow the plugin contract documentation, implement required capability declarations and operations, run the runnable external example or conformance checks, and verify artifact metadata and failure behavior.
  - **Outcome:** New models can enter the research scaffold through reviewable trusted code instead of ad hoc branches or arbitrary config imports.
  - **Covered by:** R1, R2, R3, R4, R5, R22, R23, R24, R25

---

## Evidence Used

| Evidence | Confirmed behavior or guidance | Requirement impact |
|---|---|---|
| GitHub issue #9 body and comments: https://github.com/madebymlai/aegis-rd/issues/9, https://github.com/madebymlai/aegis-rd/issues/9#issuecomment-4468465025, https://github.com/madebymlai/aegis-rd/issues/9#issuecomment-4470307429 | Issue #9 identifies target/probability/artifact risks, asks #9 to consume #2 typed target contracts, and raises multi-asset diagnostics concerns. User clarified v1 should keep global pooled behavior and avoid model-family schematics. | Requirements keep binary target/probability semantics strict, include minimal per-symbol diagnostics, and avoid per-asset/cross-sectional model families. |
| VectorBT PRO API, `FIXLB`: https://vectorbt.pro/pvt_16ebf9ef/api/labels/generators/fixlb/#vectorbtpro.labels.generators.fixlb.FIXLB | `FIXLB` is a look-ahead fixed label generator. | Model plugins must consume typed target contracts, not assume native label outputs are binary classes. |
| VectorBT PRO API, `fixed_labels_nb`: https://vectorbt.pro/pvt_16ebf9ef/api/labels/nb/#vectorbtpro.labels.nb.fixed_labels_nb | Fixed labels are percentage changes from current to future values. | `FIXLB` needs explicit target transformation before binary classification. |
| VectorBT PRO API, `TRENDLB` and `TrendLabelMode`: https://vectorbt.pro/pvt_16ebf9ef/api/labels/generators/trendlb/#vectorbtpro.labels.generators.trendlb.TRENDLB and https://vectorbt.pro/pvt_16ebf9ef/api/labels/enums/#vectorbtpro.labels.enums.TrendLabelMode | `TRENDLB` is look-ahead and supports binary, continuous, and percentage-change modes. | Binary model plugins may accept only typed binary targets; continuous trend modes fail closed in v1. |
| VectorBT PRO API, `PIVOTLB` and `Pivot`: https://vectorbt.pro/pvt_16ebf9ef/api/labels/generators/pivotlb/#vectorbtpro.labels.generators.pivotlb.PIVOTLB and https://vectorbt.pro/pvt_16ebf9ef/api/indicators/enums/#vectorbtpro.indicators.enums.Pivot | `PIVOTLB` is look-ahead and emits pivot labels with `Valley=-1` and `Peak=1`. | Sparse pivot events are not silently treated as dense binary probability targets in v1. |
| VectorBT PRO Cross-validation Applications, "Modeling": https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/applications/#modeling | VBT presents features and labels as deliberate ML design choices, uses `TRENDLB(mode="binary")` for classification, filters `X` and `y` together, and warns that normalization should run in a per-split sklearn pipeline. | Model plugin execution must be split-local and must not let preprocessing or target filtering leak across validation sets. |
| VectorBT PRO API, `PurgedKFoldCV`: https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/purged/#vectorbtpro.generic.splitting.purged.PurgedKFoldCV | Samples should have prediction and evaluation times; overlapping train/test intervals are dropped and embargo can be applied. | #9 must rely on #3 split evidence and must not train or incrementally update from validation/test data. |
| VectorBT PRO Cross-validation Splitter, "Scikit-learn": https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/splitter/#scikit-learn | Time-series observations have temporal dependency; test periods should follow training periods to avoid future-to-past leakage. | Plugin contract must preserve time-order and split-local discipline for both batch and incremental modes. |
| VectorBT PRO Cross-validation Applications, "Summary": https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/applications/#summary | `SplitterCV` is compatible with scikit-learn and many other packages, including skorch/PyTorch wrappers. | A plugin boundary is aligned with VBT: core does not need to own specific estimator classes. |
| Discord support thread, labelers are future-looking ML targets: https://discord.com/channels/918629562441695344/918630948248125512/1108837628637356242 | Maintainer says labelers are typically future-looking and used as target variables for ML training. | Label outputs must not cross into model features or target assumptions without explicit contracts. |
| Discord support thread, `trendlb` future-looking and `PIVOTINFO` non-future alternative: https://discord.com/channels/918629562441695344/918630948248125512/1104404155361153054 | Maintainer says avoid `trendlb` as a trading/module feature; it is future-looking and used for ML training. | Model contract should keep look-ahead target handling separate from feature and signal semantics. |
| Discord general thread, ML models output pandas arrays/signals for VBT: https://discord.com/channels/918629562441695344/918629563469295628/1002227531254083705 | Maintainer says an ML model just needs to output a pandas array with signals, and VBT can process pandas arrays. | Aegis can own plugin execution and emit pandas-compatible prediction panels for downstream VBT usage. |
| scikit-learn Probability calibration: https://scikit-learn.org/stable/modules/calibration.html | Calibration should use data independent from base classifier training; all classes should be present in calibration train/test subsets. | V1 records probabilities as uncalibrated and defers calibration until a leakage-safe policy is designed. |
| scikit-learn Decision threshold tuning: https://scikit-learn.org/stable/modules/classification_threshold.html | Probability estimation and decision/action thresholding are separate problems; threshold tuning should not reuse training data. | Threshold tuning stays out of #9 v1 and remains a signal/decision-policy concern. |

No direct VBT evidence was found for probability calibration policy. The calibration requirements below are therefore project/scikit-learn recommendations, not confirmed VBT behavior. No docs-vs-Discord contradiction was found for the VBT evidence above.

---

## Requirements

**Plugin Boundary**
- R1. Core model orchestration must not ship or select built-in/default model implementations in v1; every estimator must enter through a trusted registered model plugin.
- R2. Experiment config must reference models by stable registered plugin id, not arbitrary import strings, inline code, or YAML-defined estimator code.
- R3. Unknown plugin ids, unsupported plugin capabilities, or malformed plugin declarations must fail before model training or model-state mutation.
- R4. Each plugin must declare the target roles and target kinds it supports, including whether it can produce binary positive-class probabilities.
- R5. Each plugin must declare whether it supports batch fitting, live incremental updates, or both.

**Target And Probability Semantics**
- R6. Model execution must consume the typed model-ready target contract produced by #2, not native VectorBT label arrays directly.
- R7. V1 training support is limited to binary-classification supervised targets; regression/continuous, sparse-event, and regime targets must fail closed before training.
- R8. Binary probability output must be named `positive_class_probability` and must be selected by explicit positive-class mapping rather than probability-column position.
- R9. Model metadata must record positive class, observed classes, class-to-probability-column mapping, target kind, target role, target transform lineage, and whether probabilities are calibrated.
- R10. V1 probabilities must be marked uncalibrated unless a future explicit calibration contract is added; threshold tuning must remain outside #9 v1.

**Batch And Incremental Lifecycle**
- R11. Batch mode must train each validation split only from that split's training membership and must record split identity on model and prediction artifacts.
- R12. Live incremental mode must be available only for plugins that explicitly declare update capability.
- R13. Incremental updates must verify prior model-state compatibility before mutation, including plugin identity/version, target contract, feature-column contract, positive-class semantics, and relevant package/environment evidence.
- R14. Incremental updates must use only eligible past training data and must never use validation/test membership, future target windows, or unpurged look-ahead samples.
- R15. Every live incremental update must produce a new model-state artifact or manifest entry that links to prior state and records update inputs, compatibility checks, and update diagnostics.
- R16. Plugins that support batch prediction but not incremental updates must fail closed when requested in live incremental mode.

**Diagnostics And Artifacts**
- R17. Per-split model diagnostics must include train/test rows, dropped rows, class counts, feature columns, probability summaries, plugin id/version, plugin capabilities, and plugin-provided fit diagnostics when available.
- R18. Pooled/global training remains the only v1 model-family behavior, but diagnostics must include per-symbol sample counts, class counts, dropped rows, and probability summaries to expose multi-asset skew.
- R19. Model artifacts must distinguish validation split models from live updateable model state.
- R20. Native or binary model state must not be the sole source of interpretation; each model artifact must have portable metadata sufficient to understand target compatibility, class mapping, feature contract, plugin identity, and trusted-loading assumptions.
- R21. Artifact loading for model state must be treated as trusted local research behavior, not secure portable interchange.

**Plugin Authoring Contract**
- R22. The issue must add a repo-local plugin authoring guide that explains required declarations, required operations, optional incremental capability, target compatibility behavior, prediction output semantics, diagnostics, artifact metadata, and failure modes.
- R23. The issue must add a dedicated runnable external example plugin in a non-core examples area; the example must demonstrate correct registration, batch training, binary probability prediction, artifact metadata, and at least one explicit unsupported-capability failure.
- R24. The example plugin must not be auto-registered as a hidden default model; it is documentation and conformance evidence, not core behavior.
- R25. Tests or runnable checks must verify that a plugin author can follow the documented contract without relying on private core helpers or undocumented side effects.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given an experiment config references an unregistered model id, when config or pre-run validation reaches the model boundary, the run fails before training and before live model-state mutation.
- AE2. **Covers R4, R6, R7.** Given #2 emits a continuous `FIXLB` future-return target and the requested plugin supports only binary classification, when model compatibility is checked, the run fails before fitting instead of thresholding implicitly.
- AE3. **Covers R8, R9.** Given a binary target whose estimator reports classes in a non-obvious order, when predictions are produced, `positive_class_probability` is selected by the declared positive class rather than by column index.
- AE4. **Covers R10.** Given a successful binary model run with no calibration contract enabled, when artifacts are inspected, probabilities are explicitly marked uncalibrated and no tuned threshold is implied.
- AE5. **Covers R11, R14.** Given purged validation splits, when a model trains or updates for a split, it uses only the split's eligible training membership and records the split identity on the model and prediction artifacts.
- AE6. **Covers R12, R13, R15.** Given a live incremental plugin and compatible prior state, when new eligible training data is supplied, the runner verifies compatibility, updates state, writes new state lineage, and preserves the prior state as an input artifact.
- AE7. **Covers R13, R16.** Given a prior model state with incompatible feature columns or a plugin that does not support incremental updates, when live incremental mode is requested, the run fails closed before mutating model state.
- AE8. **Covers R17, R18.** Given a multi-symbol panel trained through one pooled plugin model, when diagnostics are written, aggregate and per-symbol sample counts, class counts, dropped rows, and probability summaries are visible.
- AE9. **Covers R19, R20, R21.** Given both validation split models and a live updateable model state exist in artifacts, when a reviewer inspects portable metadata, they can tell which artifacts are split evidence, which are live state, and what trusted-loading assumptions apply.
- AE10. **Covers R22, R23, R24, R25.** Given a developer follows the plugin authoring guide, when they run the external example plugin checks, the example registers explicitly, predicts binary probabilities, records required metadata, and demonstrates failure for an unsupported capability without becoming a default model.

---

## Success Criteria

- Experiment authors can choose any trusted registered model plugin without core code pretending all models are logistic regression.
- Model plugins receive explicit target contracts and cannot silently consume native VectorBT label outputs with incompatible semantics.
- Binary classifier predictions are interpretable from artifacts: positive class, observed classes, probability mapping, uncalibrated status, feature columns, and target lineage are all recorded.
- Live incremental updates are possible for capable plugins while remaining auditable, compatibility-checked, and separate from validation split artifacts.
- Plugin authors have a concrete contract and runnable example that shows how to implement a model correctly without depending on hidden core behavior.
- Downstream planning can proceed without inventing model selection policy, plugin trust boundaries, probability naming, incremental-state semantics, or calibration scope.

---

## Scope Boundaries

- No built-in/default model implementations ship in core v1.
- No AutoML as estimator search, hyperparameter optimization, or model selection is required in v1.
- No arbitrary code execution from experiment YAML, dynamic import strings, notebook snippets, or untrusted plugin sources.
- No per-asset or cross-sectional model-family schematics in v1; pooled/global training is the only supported model-family behavior.
- No regression/continuous target training, sparse-event target training, regime-target training, multiclass classification, or ranking-output contract in v1.
- No probability calibration, reliability diagram generation, or threshold tuning in v1; probabilities are recorded as uncalibrated.
- No trading-signal conversion for non-probability predictions in #9; downstream signal behavior belongs to #11.
- No custom secure model interchange format or production model registry semantics are required; trusted local research artifacts are sufficient.
- No backward-compatibility shim for the current hard-coded `long_probability` behavior unless planning discovers an existing persisted artifact consumer.

---

## Key Decisions

- Plugin-only model boundary: Core owns contracts and orchestration, while all estimator implementations come from registered trusted project-code plugins.
- No default models: Even the previous logistic-regression behavior should become either an external/example plugin or be removed from core as a special case.
- Binary-only runtime semantics in v1: This keeps the target/probability contract clear while #2, #3, and #11 stabilize adjacent meanings.
- `positive_class_probability` over `long_probability`: The probability is a model-target output first; long/short action interpretation belongs downstream.
- Live incremental lifecycle is in scope: Incremental-capable plugins can update prior state, but only with explicit compatibility checks and state lineage.
- Calibration and threshold tuning are honest non-goals: V1 records uncalibrated probabilities rather than implying more certainty than the evidence supports.
- Minimal per-symbol diagnostics: Pooled training remains simple, but multi-asset skew must be visible enough for reviewers to distrust weak evidence.
- Runnable plugin example required: Documentation alone is insufficient for a contract that third-party or project plugins must implement correctly.

---

## Dependencies / Assumptions

- Issue #2 provides the typed target contract: target kind, target role, native label provenance, transform lineage, class/positive-class metadata where applicable, and look-ahead/evaluation-window metadata.
- Issue #3 provides split evidence sufficient to decide which samples are eligible for training, validation, and live incremental updates without leakage.
- Issue #11 owns conversion from model predictions to trading entries/exits when semantics are anything beyond binary positive-class probability thresholds.
- The experiment config contract in `docs/brainstorms/2026-05-16-experiment-config-contract-requirements.md` provides the fail-fast validated config boundary this model plugin registry should reuse.
- The provenance contract in `docs/brainstorms/2026-05-16-experiment-provenance-contract-requirements.md` provides the artifact manifest, native/portable metadata, package-version, and trusted-loading expectations this work should extend.
- Current orchestration in `research/aegis_research/experiments.py` calls model compatibility checks before validation, and `research/aegis_research/validation.py` currently trains per split.
- Current `research/aegis_research/models.py` still contains fixed logistic-regression training and hard-coded `long_probability`; #9 is expected to replace that behavior with plugin contract orchestration.
- Current `research/aegis_research/config.py` constrains `MODEL_KINDS` to `logistic_regression`; #9 must replace or reinterpret that config shape around registered plugin ids.
- VBT PRO evidence is current as of 2026-05-17 and does not directly prescribe Aegis model plugin implementation details.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R2, R22][Technical] What exact registry mechanism should expose trusted model plugins while keeping config free of arbitrary imports?
- [Affects R4, R5, R22][Technical] What exact plugin declaration shape should represent supported target kinds, prediction kinds, batch capability, incremental capability, and diagnostics?
- [Affects R8, R9][Technical] Where should positive-class metadata live in the #2 target contract versus the plugin declaration, and how should mismatches fail?
- [Affects R13, R15, R20][Technical] What compatibility fingerprint is sufficient for live incremental model state without over-coupling to private plugin internals?
- [Affects R15, R19, R20][Technical] What artifact schema should distinguish split-trained models, live model state, prior-state inputs, and updated-state outputs?
- [Affects R22, R23][Technical] What repo-relative paths should hold the plugin authoring guide and runnable external example plugin?
- [Affects R25][Technical] What lightweight conformance tests or example checks should every plugin implementation be expected to pass?

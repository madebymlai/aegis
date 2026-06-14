---
date: 2026-05-18
topic: model-quality-diagnostics
source: https://github.com/madebymlai/aegis-rd/issues/22
---

# Model Quality Diagnostics

## Summary

Add core-owned, metrics-only diagnostics that help reviewers judge whether a model plugin's standardized `positive_class_probability` output shows learnable signal. This first slice keeps survival gates portfolio-first, avoids threshold tuning, and does not expand the plugin API.

---

## Problem Frame

The built-in `aegis.sklearn_logistic` plugin can complete the full `aerd` experiment pipeline, but recent smoke runs were rejected by out-of-sample portfolio gates. A rejected survival report currently tells reviewers that the strategy failed portfolio thresholds, but it does not show whether the model had no predictive skill, produced poor probabilities, overfit train membership, or simply failed later signal/portfolio conversion.

Adding a stronger estimator before answering that question risks hiding feature, label, probability, or validation problems behind more model complexity. The next useful product step is evidence: reviewers need model/probability diagnostics that are separate from portfolio metrics and safe to compare across plugins that already satisfy the standardized probability contract.

---

## Actors

- A1. Researcher: Reviews experiment runs and decides whether to tune features, labels, thresholds, or model families.
- A2. Experiment iteration agent: Runs `aerd run --json`, inspects artifacts, and reports why a run needs follow-up.
- A3. Plugin author: Maintains model plugins while relying on a stable fit/predict probability contract.
- A4. Run reviewer: Inspects manifests and reports without loading private native artifacts.

---

## Key Flows

- F1. Review model quality after a completed run
  - **Trigger:** A run completes and writes validation artifacts plus a survival report.
  - **Actors:** A1, A2, A4
  - **Steps:** Open the run summary, inspect model/probability diagnostics by split and set, compare train versus test behavior, and decide whether the model output itself looks useful enough for downstream signal/portfolio analysis.
  - **Outcome:** The reviewer can distinguish weak model/probability evidence from portfolio-only rejection without adding a new model plugin.
  - **Covered by:** R1, R2, R3, R5, R8

- F2. Keep plugin authors out of diagnostics scope
  - **Trigger:** A plugin that already emits standardized positive-class probabilities is used in validation.
  - **Actors:** A2, A3
  - **Steps:** The plugin fits and predicts through the existing contract; core computes generic diagnostics from standardized outputs and labels.
  - **Outcome:** Diagnostics improve run evidence without requiring plugin-specific diagnostic methods or payloads.
  - **Covered by:** R4, R6, R7

---

## Requirements

**Diagnostic content**
- R1. Diagnostics must report train/test class balance per validation split, including enough counts to identify one-class or severely imbalanced split/set evidence.
- R2. Diagnostics must report generic binary-classification quality metrics for train and test sets where statistically applicable, including accuracy, precision, recall, and ROC AUC.
- R3. Diagnostics must report probability-quality metrics and summaries for train and test sets where applicable, including log loss, Brier score, probability distribution summaries, and calibration-bin evidence.
- R4. Diagnostics must be computed by core from standardized model outputs, target labels, and split membership; no plugin-specific diagnostic API is required or optional in this issue.

**Artifacts and report surface**
- R5. Validation artifacts must expose model-quality diagnostics separately from portfolio metrics so reviewers can inspect model evidence without treating it as trading performance.
- R6. Diagnostics must remain portable public evidence: they must not require loading private native model or portfolio artifacts and must not serialize raw model state.
- R7. Diagnostics must preserve split identity and train/test set identity so reviewers can compare train/test drift and per-split instability.
- R8. The survival report may organize or link to model diagnostics, but it must not convert diagnostics into a new survival verdict, likely-cause label, or recommended action.

**Contract boundaries**
- R9. Existing survival gates remain portfolio-first; rejected or inconclusive research verdicts must not change because model diagnostics were added.
- R10. Diagnostics must not perform threshold sweeps, threshold optimization, automatic threshold selection, probability calibration, or model-family selection in this issue.
- R11. Diagnostics must work for any trusted registered plugin that produces the existing `positive_class_probability` output for binary supervised targets.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R7.** Given a split has both positive and negative classes in train and test, when validation completes, the diagnostics show class counts and binary-classification metrics for both sets under that split identity.
- AE2. **Covers R2, R3.** Given a test set has only one observed class, when diagnostics are written, metrics that require both classes are marked unavailable or insufficient-evidence rather than failing the run or fabricating a value.
- AE3. **Covers R3, R5, R6.** Given a plugin emits uncalibrated positive-class probabilities, when artifacts are inspected, probability summaries and calibration-bin evidence are available as public diagnostics without loading native model state.
- AE4. **Covers R4, R11.** Given two different plugins both emit valid `positive_class_probability` panels, when validation runs, core computes the same generic diagnostic categories for both without plugin-specific methods.
- AE5. **Covers R8, R9.** Given model diagnostics look weak but portfolio metrics pass, or diagnostics look decent but portfolio metrics fail, when the survival report is read, the existing portfolio-first survival status remains the only verdict.
- AE6. **Covers R10.** Given a run uses default entry and exit thresholds, when model-quality diagnostics are written, they do not test alternate thresholds, choose a replacement threshold, or mutate experiment config.

---

## Success Criteria

- Reviewers can tell whether a rejected run also lacked basic model/probability evidence before deciding to tune features, labels, thresholds, or plugins.
- Plugin authors can keep the current fit/predict contract and do not need to maintain model-specific diagnostic payloads.
- Agents can inspect public artifacts and summarize model quality without loading private native artifacts or inferring from portfolio metrics alone.
- Downstream planning can proceed without inventing whether this issue includes calibration, threshold sweeps, plugin hooks, or new survival gates.

---

## Scope Boundaries

- No new required or optional plugin diagnostics API.
- No threshold sweep, threshold optimization, adaptive thresholds, or automatic threshold recommendations.
- No probability calibration policy, calibrated probability artifact, or reliability-diagram requirement beyond generic calibration-bin evidence.
- No likely-cause label such as model-quality failure, thresholding failure, or portfolio-friction failure.
- No recommended next action in the survival report.
- No promotion of model diagnostics into survival gates.
- No new model plugin, stronger estimator, hyperparameter optimization, or model-family selection.
- No support for non-binary, multiclass, regression, ranking, sparse-event, or regime-target diagnostics in this issue.

---

## Key Decisions

- Core-owned diagnostics: Generic diagnostics should live above the plugin boundary because the standardized probability output already gives core enough information for the first useful slice.
- Metrics-only report stance: The feature should add evidence, not causal attribution or action advice, because metrics can disagree across train/test, probability quality, and portfolio performance.
- Model-only first slice: Threshold and portfolio sensitivity are valuable, but they answer a downstream question; this issue first establishes whether the model/probability layer has usable evidence.
- Stable plugin contract: Optional hooks are deferred because even optional diagnostic payloads create a second interpretation channel before generic diagnostics have proven insufficient.

---

## Dependencies / Assumptions

- The existing model contract provides standardized `positive_class_probability` panels and metadata for binary supervised targets.
- Existing signal requirements intentionally deferred threshold optimization and probability calibration in `docs/brainstorms/2026-05-17-signal-generation-conflict-semantics-requirements.md`.
- Existing model requirements intentionally deferred probability calibration and reliability diagrams in `docs/brainstorms/2026-05-17-model-plugin-target-probability-contract-requirements.md`; this issue may add calibration-bin evidence as diagnostics, not a calibration policy.
- `manifest.json` remains the source of truth for artifact inventory; CLI JSON should not become the full diagnostic transport.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R2, R3][Technical] Define exact metric availability behavior for one-class sets, all-NaN probabilities, empty eligible rows, and non-finite probability values.
- [Affects R3][Technical] Choose the first calibration-bin shape and minimum bin/count behavior without implying probabilities are calibrated.
- [Affects R5, R8][Technical] Decide how much of the diagnostics the survival report embeds directly versus linking or summarizing from validation artifacts.

---
title: Preserve VectorBT label semantics before model target derivation
date: 2026-05-17
category: logic-errors
module: research/aegis_research/labels.py
problem_type: logic_error
component: service_object
symptoms:
  - "VectorBT FIXLB, TRENDLB, and PIVOTLB outputs were collapsed into binary target panels too early."
  - "Native label outputs and model-ready targets were not separated clearly."
  - "Target transform lineage, split-safety metadata, and look-ahead risk were not explicit in artifacts."
root_cause: logic_error
resolution_type: code_fix
severity: high
related_components:
  - "research/aegis_research/config.py"
  - "research/aegis_research/models.py"
  - "research/aegis_research/provenance/experiment_artifacts.py"
tags:
  - vectorbt
  - labels
  - target-contract
  - provenance
  - lookahead
  - split-safety
---

# Preserve VectorBT label semantics before model target derivation

## Problem

The label pipeline treated native VectorBT label outputs and sklearn-ready targets as the same thing. `FIXLB`, `TRENDLB`, and `PIVOTLB` outputs were converted into binary panels before the pipeline preserved native values, parameter coordinates, transform lineage, target type, diagnostics, or look-ahead safety metadata.

This made downstream training possible, but it erased the evidence needed to audit what the target actually meant.

## Symptoms

- `FIXLB` future-return labels were immediately thresholded into classes.
- `TRENDLB` modes beyond binary could not be represented as continuous or percentage-change style targets.
- `PIVOTLB` valley and peak semantics were hidden behind a generic positive-value binary transform.
- Parameter sweeps risked implicit target selection because native parameter levels were not part of the target contract.
- Validation could proceed on look-ahead labels without an explicit diagnostic opt-in.
- Public artifacts did not contain enough target lineage or portable target values to audit a run without loading private native objects.

## What Didn't Work

- Keeping `build_labels` as a simple DataFrame-returning helper was not enough. The model still needs a DataFrame, but the research loop also needs native labels, lineage, diagnostics, and target schema evidence.
- Hiding VectorBT params with `hide_params=True` made artifacts easier to read, but it removed parameter identity from the output contract.
- Treating all label outputs as binary classification targets conflated different semantics: future returns, trend regimes, continuous trend labels, and sparse pivot events.
- Marking reports as non-decision-grade after validation did not fully solve leakage risk. Without a fail-closed compatibility gate, expensive and potentially misleading validation artifacts could still be produced by default.
- Session history search found no additional relevant prior sessions for this specific fix.

## Solution

Preserve native label generation as a separate stage, then derive exactly one model-ready target through an explicit selected coordinate and transform.

The final boundary object keeps the model target small while preserving the native contract:

```python
@dataclass(frozen=True)
class LabelResult:
    labels: pd.DataFrame
    metadata: dict[str, Any]
    native_labels: pd.DataFrame
    lineage: dict[str, Any]
    diagnostics: dict[str, Any]
    target_schema: dict[str, Any]
    split_safety: dict[str, Any]
    evaluation_evidence: LabelEvaluationEvidence
    native_object: Any | None = None
```

The label builder now follows a native-first sequence:

```python
native_object = _run_native_label_generator(close, config, high=high, low=low)
native_labels = _label_panel(native_object.labels)
selected_params = _selected_params(config)
selected_native = _select_native_target(native_labels, close, config.kind, selected_params)
target = _derive_target(selected_native, config)
```

The config contract separates generator params from target selection and target transforms:

```yaml
labels:
  generator:
    kind: fixlb
    params:
      n: [1, 2]
  target:
    role: supervised_target
    select:
      params:
        n: 2
    transform:
      name: threshold_future_return
      params:
        threshold: 0.0
```

Native labels can preserve every generated parameter coordinate, while the model path receives only the selected target. The target schema records the derivation:

```python
{
    "schema_version": "label_target.v1",
    "target_kind": "binary_classification",
    "target_role": "supervised_target",
    "source": {
        "generator_kind": "fixlb",
        "native_output": "labels",
        "selected_params": {"n": 2},
    },
    "transform": {
        "name": "threshold_future_return",
        "version": 1,
        "params": {"threshold": 0.0},
    },
    "split_safety": {
        "purging_required": True,
        "purging_applied": False,
    },
}
```

The model compatibility gate rejects unsupported target kinds, regime roles, and unpurged look-ahead labels. There is no diagnostic-validation escape hatch for look-ahead experiment validation:

```python
if _requires_purging_proof(split_safety):
    return _incompatible(
        diagnostics,
        "look-ahead labels require purged split evidence before validation",
    )
```

Runs now persist public label metadata, lineage, diagnostics, target schema, compatibility output, and a portable selected target CSV. Native VectorBT objects remain private artifacts with public sidecars.

## Why This Works

The root bug was ordering: the pipeline transformed native evidence into a model target before preserving enough information to audit or validate the transformation. Reversing that order makes every semantic boundary explicit.

The durable pattern is:

```text
VectorBT native labels
  -> explicit selected native slice
  -> explicit transform
  -> model-ready target
  -> schema + lineage + diagnostics + split-safety artifacts
```

This prevents recurrence because each important fact has one named home:

- `native_labels` preserves VectorBT output semantics and parameter levels.
- `target.select.params` records which native coordinate became the model target.
- `target.transform` records how native values became model labels.
- `target_schema.target_kind` prevents incompatible targets from reaching sklearn.
- `split_safety` records look-ahead risk before split construction and validation.
- `evaluation_evidence` records row-level prediction and evaluation times for purged split construction.
- `labels.compatibility` records fail-closed diagnostics before training or validation proceeds.
- `labels.target` gives agents and reviewers a portable target panel without loading private pickles.

The contract now feeds purged CV for fixed-horizon `FIXLB` labels. Variable-confirmation labels such as `TRENDLB` and `PIVOTLB` remain fail-closed until they provide exact confirmation-time evidence.

## Prevention

- Preserve native VectorBT outputs before deriving model-ready panels.
- Treat target transforms as explicit contract fields, not hidden generator behavior.
- Require target selection when native generator params have multiple values.
- Validate scalar/default target selection at config load, before run side effects.
- Reject unsupported target kinds at the model boundary rather than coercing them into binary labels.
- Fail closed for unpurged look-ahead labels; exploratory metrics should not share the survival-report validation path.
- Persist portable target artifacts alongside native private artifacts so agents can inspect runs without loading version-sensitive pickles.
- Add tests that assert native semantics, not only that derived outputs are `{0, 1}`.

Useful regression tests include:

```python
assert set(result.native_labels.columns.get_level_values("fixlb_n")) == {1, 2}
assert result.target_schema["source"]["selected_params"] == {"n": 2}
pd.testing.assert_frame_equal(result.labels, expected_n_2_target)
```

```python
diagnostics = target_model_compatibility(
    labels,
    ModelConfig(min_train_samples=1),
    {"target_kind": "continuous", "target_role": "supervised_target"},
    phase="pre_split",
)

assert diagnostics["compatible"] is False
```

```python
with pytest.raises(ConfigValidationError, match="look-ahead labels require purged_kfold"):
    resolve_experiment_config(config_with_holdout_fixlb)
```

## Related Issues

- GitHub issue: `madebymlai/aegis-rd#2`
- PR: `madebymlai/aegis-rd#18`
- Follow-up: `madebymlai/aegis-rd#3` for broader purged-CV hardening and future confirmation-time oracles.
- Follow-up: `madebymlai/aegis-rd#9` for broader model target and probability support.
- Related solution: `docs/solutions/best-practices/vectorbt-indicatorfactory-output-shape-contract-2026-05-17.md`
- Related solution: `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`
- Related solution: `docs/solutions/best-practices/vectorbt-combine-params-conditions-levels-2026-05-17.md`

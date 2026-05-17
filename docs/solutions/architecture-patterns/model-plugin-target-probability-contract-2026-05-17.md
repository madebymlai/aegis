---
title: Model Plugin Target and Probability Contract
date: 2026-05-17
category: architecture-patterns
module: research/aegis_research
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - Replacing hard-coded research model implementations with plugin execution
  - Persisting model artifacts that must be interpreted outside native state
  - Producing classifier probabilities from typed model-ready targets
related_components:
  - development_workflow
  - testing_framework
  - documentation
tags:
  - model-plugins
  - target-contract
  - probability-semantics
  - artifact-provenance
  - trusted-registration
  - vectorbt
---

# Model Plugin Target and Probability Contract

## Context

The model layer previously mixed estimator choice, target meaning, probability interpretation, and native artifact persistence inside core research code. That was workable for a hard-coded sklearn logistic-regression path, but it became unsafe once labels carried explicit VectorBT-derived target semantics and artifacts needed to be consumed outside the original training path.

The durable boundary is now plugin-only model execution. Core Aegis owns the trusted contract around config validation, target compatibility, split-local training membership, probability validation, diagnostics, provenance, and export metadata. Plugins own estimator behavior through `fit` and `predict`.

## Guidance

Keep experiment YAML declarative and inert. YAML may select a registered plugin id and JSON-like params, but it must not import Python code, define estimators, reference classes, request mutable state updates, or choose hidden built-in model kinds.

```yaml
model:
  plugin_id: examples.sklearn_logistic
  min_train_samples: 100
  params:
    max_iter: 1000
    random_state: 42
```

Register trusted model code before config resolution. The resolved config should carry a frozen registry snapshot so unknown plugin ids, duplicate plugin ids, malformed declarations, and invalid plugin params fail before run directories or artifacts are created.

```python
registry = ModelRegistry()
registry.register(
    ModelPluginDefinition(
        declaration=ModelPluginDeclaration(
            id="examples.sklearn_logistic",
            version="1.0.0",
            prediction_outputs=("positive_class_probability",),
            state_schema_version="sklearn_logistic.v1",
            trusted_loading=True,
        ),
        plugin=SklearnLogisticPlugin(),
        validate_params=validate_params,
    )
)

resolved = load_experiment_config(path, model_registry=registry.freeze())
```

Treat the typed target schema as the source of truth. The shipped v1 plugin path supports supervised binary-classification targets. A binary target schema must define exactly two classes and a `positive_class`; continuous targets, sparse events, regimes, multiclass labels, regression targets, ranking outputs, and distributional outputs should fail closed until a future explicit contract supports them.

Select probabilities by class mapping, never by column position. Plugins may return class-specific probability columns, but they must report `observed_classes` and `class_probability_columns`. Core maps the target schema's `positive_class` to the standardized `positive_class_probability` output.

```python
columns = {class_label: f"class_{class_label}_probability" for class_label in estimator.classes_}

return ModelPredictionResult(
    probabilities=pd.DataFrame(
        estimator.predict_proba(dataset.features),
        index=dataset.row_index,
        columns=[columns[class_label] for class_label in estimator.classes_],
    ),
    observed_classes=tuple(estimator.classes_),
    class_probability_columns=columns,
)
```

Keep validation split-local. Fit one model per validation split using only that split's training rows. Prediction datasets are feature-only, validation/test labels remain in core validation, and `(timestamp, symbol)` row indexes must survive plugin calls and probability outputs.

Persist public model metadata as the interpretation layer. Native model state is useful for trusted local replay, but the durable artifact contract is the public sidecar: plugin id and version, registry fingerprint, target schema, classes, positive class, probability output name, feature columns hash, split label, training counts, and trusted-loading assumptions. Do not put raw params, plugin diagnostics blobs, secrets, local paths, or mutable lifecycle state into public metadata.

Export bundles should be producer-side, immutable, and prediction-only. The export path copies a completed validation model artifact, writes `model_export_bundle.json`, rejects existing output directories, rejects incomplete artifacts, validates metadata sidecars and schema versions, and refuses untrusted native state. Consumers must register reviewed plugin code and validate metadata before loading native state.

Make artifact writes failure-aware. Plan artifacts before writing, write through temp files with fsync and atomic replace, mark failed artifacts when writes fail, and remove partial files so a failed run cannot look complete.

## Why This Matters

This contract prevents research failures that are hard to detect after the fact:

- `predict_proba(...)[..., 1]` being assumed to mean a long-side probability when it only means the estimator's second class column.
- Continuous future returns, sparse events, or regime labels being silently treated as binary classifier targets.
- Validation split models being mistaken for mutable deployment state.
- External consumers loading a native pickle/joblib file without knowing plugin identity, target schema, feature schema, class mapping, or trust assumptions.
- YAML becoming an arbitrary-code-loading surface or a source of hidden estimator defaults.
- Partial artifacts remaining in manifests as if the run completed successfully.

The contract also keeps action semantics in the right layer. `positive_class_probability` is a model output tied to target classes. Long/short decisions, thresholds, entries, and exits belong to downstream signal policy.

## When to Apply

- Adding a new sklearn pipeline, PyTorch model, wrapper, or custom classifier to research validation.
- Changing how model-ready targets are derived from VectorBT labels.
- Emitting probabilities that feed signals, backtests, exports, or another runtime project.
- Persisting artifacts that must remain understandable after code changes.
- Adding config fields that could otherwise imply imports, estimator construction, state mutation, or hidden defaults.
- Adding support for currently unsupported target or lifecycle meanings, such as regression, multiclass classification, calibrated probabilities, threshold tuning, per-symbol model families, live incremental updates, or production registry behavior.

## Examples

Before, model choice and probability meaning were implicit:

```yaml
model:
  kind: logistic_regression
  min_train_samples: 100
```

```python
long_probability = estimator.predict_proba(features)[:, 1]
```

After, the model is selected by trusted registration and the probability name reflects target semantics:

```yaml
model:
  plugin_id: examples.sklearn_logistic
  min_train_samples: 100
  params:
    max_iter: 1000
```

```python
positive_class_probability = predict_positive_class_probability(
    model,
    indicators,
    target_schema=target_schema,
    split_label=split.label,
    set_name="test",
)
```

Before, native model state could be the only meaningful artifact:

```text
model.joblib
```

After, native state is bound to public metadata and export evidence:

```text
splits/split_0/model.joblib
splits/split_0/model.joblib.metadata.json
manifest.json
model_export_bundle.json
```

The export bundle states the consumer contract explicitly:

```json
{
  "schema_version": "model_export_bundle.v1",
  "mode": "prediction_only",
  "immutable": true,
  "consumer_contract": {
    "must_register_plugin_id": "examples.sklearn_logistic",
    "must_match_plugin_version": "1.0.0",
    "must_validate_registry_fingerprint": "...",
    "must_validate_feature_columns_hash": "...",
    "probability_output_name": "positive_class_probability",
    "calibrated": false,
    "native_state_loading_is_trusted_code": true
  }
}
```

The completed implementation was verified by `uv run ruff check research/aegis_research tests/research/aegis_research`, `uv run pytest` with 203 passing tests, and `git diff --check` before commit `595266b feat(research): add model plugin contract` was pushed.

## Related

- `docs/model-plugins.md` documents the public plugin authoring and export contract.
- `examples/model_plugins/README.md` and `examples/model_plugins/sklearn_logistic_plugin.ipynb` show explicit registration and pure-Python adaptation.
- `research/aegis_research/model_contracts.py` defines the plugin, dataset, fit, and prediction contracts.
- `research/aegis_research/model_registry.py` defines explicit registration, frozen registry snapshots, and registry fingerprints.
- `research/aegis_research/models.py` enforces target compatibility, positive-class probability mapping, split-local training, and model metadata.
- `research/aegis_research/model_export.py` writes immutable prediction-only producer bundles.
- `research/aegis_research/provenance/experiment_artifacts.py` writes sidecar-bound native model artifacts and failure-aware public artifacts.
- `docs/solutions/logic-errors/vectorbt-label-contract-target-lineage-2026-05-17.md` explains the upstream label target lineage contract this model boundary consumes.
- `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md` explains the fail-fast config and provenance pattern this contract extends.

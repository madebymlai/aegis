# Model Plugins

Aegis model execution is plugin-only in v1. Run YAML selects a stable train-mode model ref; it never imports Python code, defines estimators, or requests mutable model-state updates.

## Config Contract

```yaml
train:
  model:
    source: plugin
    id: aegis.sklearn_logistic
    min_train_samples: 100
    params:
      max_iter: 1000
      random_state: 42
```

Model training is split-local batch validation in v1. The `source` field is retained so future model sources can be added deliberately, but `plugin` is the only accepted source today. This repo does not implement live updates, incremental fitting, local model file loading, or runtime importer behavior.

## Registration Contract

Trusted code constructs a `ModelRegistry`, registers `ModelPluginDefinition` objects, freezes the registry, and passes that snapshot into config resolution or `run_training`/`run_experiment`.

Core Aegis ships a default registry with the baseline `aegis.sklearn_logistic` plugin. Use `make_default_model_registry()` from `research.aegis_research.model_plugins` in Python runners; the `aerd` CLI registers this default registry automatically for `aerd run --train` validation. Default `aerd run` is reserved for playbook-backed or component-backed strategy/research sweeps and rejects model-training configs with guidance to use `aerd run --train`.

Plugins declare:

- Stable plugin id and version.
- Supported target roles and target kinds.
- Prediction outputs including `positive_class_probability`.
- Batch support.
- Native state schema version and trusted-loading assumptions.
- Optional side-effect-free parameter validation.

## Execution Contract

Core Aegis owns panel-to-tabular shaping, target compatibility checks, split-local training membership, positive-class probability validation, diagnostics, and artifacts.

Plugins own estimator behavior through two methods:

```python
fit(dataset, *, params, context) -> ModelFitResult
predict(state, dataset, *, params, context) -> ModelPredictionResult
```

`dataset.features` is a pooled `(timestamp, symbol)` table. `fit` receives target labels only for the split's training rows. `predict` receives feature-only data and must not rely on validation/test labels.

Probability output must be selected by class mapping. A plugin may return class-specific columns, but it must report `observed_classes` and `class_probability_columns`; core maps the target schema's `positive_class` to the standardized `positive_class_probability` panel.

## Export Contract

Use `export_model_bundle(run_dir, model_artifact_id=..., output_dir=...)` to produce an immutable prediction-only bundle for another project. The bundle includes public compatibility metadata plus a trusted native state copy. The consuming project must register reviewed plugin code and validate metadata before loading native state.

See `docs/examples/model_plugins/sklearn_logistic_plugin.ipynb` for a runnable explicit-registration example and `docs/examples/model_plugins/README.md` for a pure-Python adaptation path.

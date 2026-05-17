# Model Plugin Examples

`sklearn_logistic_plugin.ipynb` shows a complete external plugin path:

- Define a sklearn-backed plugin outside core Aegis.
- Register it explicitly in a `ModelRegistry`.
- Resolve an experiment config against the frozen registry.
- Run batch validation and optionally export a prediction-only bundle.

For pure Python, copy the plugin class and `build_registry()` function from the notebook into a normal module, import that module from your runner script, then call `resolve_experiment_config(..., model_registry=registry)` before `run_experiment(...)`.

Do not put import paths, estimator definitions, or plugin code in YAML.

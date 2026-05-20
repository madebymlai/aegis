# Model Plugin Examples

`sklearn_logistic_plugin.ipynb` shows a complete external plugin path:

- Define a sklearn-backed plugin outside core Aegis.
- Register it explicitly in a `ModelRegistry`.
- Resolve a canonical train lane config against the frozen registry.
- Run batch validation and optionally export a prediction-only bundle.

For pure Python, copy the plugin class and `build_registry()` function from the notebook into a normal module, import that module from your runner script, then pass `registry.freeze()` to `load_lane_config(...)` or `resolve_lane_config(..., expected_lane="train", model_registry=...)` before training.

Do not put import paths, estimator definitions, or plugin code in YAML.

For a runnable end-to-end scaffold experiment walkthrough, use `docs/examples/scaffold_experiment_walkthrough.ipynb`. That notebook uses an inline config and explicit registry setup rather than a tracked baseline YAML.

For ordinary Aegis runs, prefer the built-in `aegis.sklearn_logistic` plugin from `research.aegis_research.model_plugins` instead of copying this example.

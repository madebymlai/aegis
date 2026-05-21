# Components

Components are reviewed Python percent-cell files under `research/components/{indicators,strategies}/`. Forward `run` configs name component IDs directly:

```yaml
strategy:
  id: demo.cross

indicators:
  - id: demo.ma
```

Each entry may carry `params`, `lock_id`, or `candidate_id`. `lock_id` and `candidate_id` are mutually exclusive. Source selectors and indicator `ids` batching are removed so each lockable component slot is explicit.

YAML never imports Python, names modules, embeds formulas, or points at arbitrary files. Discovery reads only literal `COMPONENT_MANIFEST` and `COMPONENT_CALLABLE` metadata without executing the component file. Callable code loads only after validation selects a known ID under the fixed component root.

Component manifests declare:

- `input_names`: exact VBT raw-data features the component reads, such as `Close` or `High`.
- Indicator `output_names`: named outputs available to strategies.
- Strategy `consumes_outputs`: named indicator outputs required by the strategy.
- `param_names`: lockable/optimizable parameter names.
- `defaults`: fixed values for one-candidate execution.
- `param_space_callable`: optional callable returning a mapping of parameter names to `vbt.Param` axes.

Indicator callables receive a market-data bundle and request declared raw features through `data.feature("FeatureName")`. Strategy callables receive an inputs object with `inputs.data`, `inputs.indicators`, and `inputs.metadata`; they emit aligned `entries` and `exits` only. Portfolio sizing, costs, direction, and timing remain config-owned.

Runs with no unlocked axes still execute through the native optimization path as one candidate. Runs with unlocked component params compose all indicator and strategy axes into one VBT-native grid. Promotion locks resolve persisted candidate params into constants before execution.

Local component files are ignored by git by default except placeholder READMEs. Ignored files are not secret management; do not store credentials in local research code. Public component examples live under `docs/examples/components/`.

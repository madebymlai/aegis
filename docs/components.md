# Components

Promoted components are reviewed Python files under `research/components/{labels,indicators,strategies}/`. `run` configs select strategy by one explicit source ref and indicators by grouped source blocks; playbook refs use the same `source` discriminator:

```yaml
strategy:
  source: component
  id: demo.cross

indicators:
  - source: component
    ids: all
  - source: component
    ids: [demo.ma]
```

YAML never imports Python, names modules, embeds formulas, or points at arbitrary files. Discovery reads only literal `COMPONENT_MANIFEST` and `COMPONENT_CALLABLE` metadata without executing the component file. Callable code loads only after validation selects a known ID under the fixed component root.

Indicator components should use the same VectorBT-native helper path as built-ins (`vbt.MA`, `vbt.RSI`, custom `vbt.IF`, primitive returns/volatility normalization). Label, indicator, and strategy manifests declare exact VBT raw-data dependencies in `input_names`, for example `input_names: ["Close"]` or `input_names: ["High", "Low", "Close"]`. Indicator and label callables receive a market-data bundle with `data.open`, `data.high`, `data.low`, `data.close`, and `data.volume` panels; use the fields declared by the component manifest. Components that need another provider feature should call `data.feature("FeatureName")` and let the data contract fail if it is unavailable or not configured. Label components should preserve the native label path (`vbt.FIXLB`, `vbt.TRENDLB`, `vbt.PIVOTLB`) and target lineage. Strategy components receive a strategy bundle and should read prices through `bundle.data`; they emit aligned `entries` and `exits` only. Portfolio sizing, costs, direction, and timing remain config-owned. Component callables own their defaults and sweeps directly; lane configs do not pass per-run params into component code.

`aerd run --train` uses top-level component indicator selections plus train-specific label and model refs. Model refs keep a `source` field for future extension, but v1 accepts only `source: plugin`:

```yaml
indicators:
  - source: component
    ids: [demo.ma]

train:
  label:
    source: component
    id: demo.fixlb
  model:
    source: plugin
    id: aegis.sklearn_logistic
```

Local component files are ignored by git by default except the placeholder READMEs. Ignored files are not secret management; do not store credentials in local research code. Public component examples live under `docs/examples/components/`.

# Components

Promoted components are reviewed Python files under `research/components/{labels,indicators,strategies}/`. `run` configs select strategy and indicator components by explicit source ref; playbook refs use the same source-ref shape with `source: playbook`:

```yaml
strategy:
  source: component
  id: demo.cross

indicator_refs:
  - source: component
    id: all
  - source: component
    id: demo.ma

label:
  source: component
  id: demo.fixlb
```

YAML never imports Python, names modules, embeds formulas, or points at arbitrary files. Discovery reads only literal `COMPONENT_MANIFEST` and `COMPONENT_CALLABLE` metadata without executing the component file. Callable code loads only after validation selects a known ID under the fixed component root.

Indicator components should use the same VectorBT-native helper path as built-ins (`vbt.MA`, `vbt.RSI`, custom `vbt.IF`, primitive returns/volatility normalization). Label components should preserve the native label path (`vbt.FIXLB`, `vbt.TRENDLB`, `vbt.PIVOTLB`) and target lineage. Strategy components should emit aligned `entries` and `exits` only; portfolio sizing, costs, direction, and timing remain config-owned.

`aerd run --train` uses the same source-ref shape in its `train:` section. Model refs keep a `source` field for future extension, but v1 accepts only `source: plugin`:

```yaml
train:
  label:
    source: component
    id: demo.fixlb
  model:
    source: plugin
    id: aegis.sklearn_logistic
```

Local component files are ignored by git by default except the placeholder READMEs. Ignored files are not secret management; do not store credentials in local research code. Public component examples live under `docs/examples/components/`.

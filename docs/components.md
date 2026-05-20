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

Component files are Jupytext-compatible Python percent-cell sources. Use purposeful cells: a broad overview cell that explains the promoted idea and source data, an imports/definitions cell when needed, a literal metadata cell, and a `# %% main ...` compute cell. The callable named by `COMPONENT_CALLABLE` must have a docstring explaining the indicator, label, or strategy logic.

Indicator components should use the same VectorBT-native helper path as built-ins (`vbt.MA`, `vbt.RSI`, custom `vbt.IF`, primitive returns/volatility normalization). Label, indicator, and strategy manifests declare exact VBT raw-data dependencies in `input_names`, for example `input_names: ["Close"]` or `input_names: ["High", "Low", "Close"]`. Indicator and label callables receive a market-data bundle and request every declared raw feature through `data.feature("FeatureName")`; Aegis does not expose hardcoded OHLCV bundle fields. Label components should preserve the native label path (`vbt.FIXLB`, `vbt.TRENDLB`, `vbt.PIVOTLB`) and target lineage. Strategy components receive a strategy bundle and should read prices through `bundle.data.feature("FeatureName")`; they emit aligned `entries` and `exits` only. Portfolio sizing, costs, direction, and timing remain config-owned. Component callables own fixed reviewed defaults/params. They must not emit parameter sweeps, candidate grids, batched candidate axes, or consume playbook indicator surfaces through the component runner; configs that pair a component strategy with playbook indicators are rejected before run execution. Use a playbook for sweeps, then manually promote one composed winner into fixed indicator and strategy components. Lane configs do not pass per-run params into component code.

Manual promotion starts from a composed leaderboard row: the indicator side identifies the source/candidate/params to freeze into an indicator component, and the strategy side identifies the source/candidate/params to freeze into a strategy component. Aegis does not generate those component files automatically; a component author creates reviewed source files and reruns with `source: component` refs to verify the promoted pair.

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

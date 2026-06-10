# Local Run Configs

Local `aerd run` configs are ignored by git by default. Directory layout carries no semantics: subdirectories are free organization, the config is always selected by the explicit path passed to `aerd run <config>`, and no mode is inferred from folders or CLI flags.

Use `aerd run <config>` for strategy or research sweeps over direct component refs. Inspect discoverable component IDs with `aerd show components` and splitter methods with `aerd show splitters <method>`.

## Schema (version 8)

A run config must declare `schema_version: 8` exactly. Three sections have no silent defaults: `data.arrays` is required (no implicit OHLCV), and `portfolio.gross_cap` and `portfolio.direction` are required (no implicit long-only). An `optimization` block is required; fixed/non-optimized strategy runs are removed from the forward run contract.

```yaml
schema_version: 8
name: example_ma_cross

data:
  source: yf            # synthetic | csv | any VBT remote source (e.g. yf)
  symbols: [SPY, TLT]   # required for remote sources
  start: '2018-01-01'   # start/end/timeframe required for remote sources
  end: '2025-01-01'
  timeframe: 1D
  arrays: [OHLCV]       # required; OHLCV expands to Open/High/Low/Close/Volume.
                        # Other entries are source-native feature names, e.g. "Adj Close".

portfolio:
  gross_cap: 1.0        # required
  direction: longonly   # required: longonly | shortonly | both
  fees: 0.001
  slippage: 0.0005

strategy:
  id: example.ma_cross  # component id; optional params: {...} fixes declared params

indicators:
  - id: example.ma

ranking:
  metric: sharpe_ratio

optimization:
  search: grid          # grid | random; random additionally requires
                        # random_subset and seed (deterministic sampled evidence)
  split:
    method: from_rolling
    params:
      length: 252
      offset: 252
      split: 0.8
    max_splits: 100
```

Optional sections: `report` (OOS gates `min_oos_sharpe`, `max_oos_drawdown`, `min_oos_trades`, and the annualization calendar `freq`/`year_freq`), `output_dir` (default `runs`), and `lock` (below).

Put split policy under `optimization.split`; top-level `split` and `candidate_grid` are unknown to the forward schema. `optimization.split.method` is the exact `vbt.Splitter` constructor method, and `optimization.split.params` are kwargs for that method. Inspect available methods and signature-derived params with `aerd show splitters <method>` before authoring YAML.

Compatible VBT splitter methods, such as `from_rolling` and `from_purged_kfold`, use the same run scoring pipeline when VBT can build exactly two non-overlapping sets per split from the source index plus params. The first set is always treated as the selection set, the second as the held-out set; `set_labels` is not user-configurable.

## Locks

A top-level `lock` reproduces one prior Candidate: every component takes its parameters from that Candidate instead of searching. Use the scalar handle `lock: <run_id>` (role defaults to `best`), `lock: <run_id>:<best|median|worst>`, or the exact mapping form `lock: {run_id: ..., candidate_id: <candidate_key>}`. There are no per-component lock fields; to freeze a single component while the rest optimize, fix its values with that component's `params:`.

Ignored files are not secret management. Do not put API keys, provider tokens, or credentials directly in local YAMLs or notebooks. Use environment-backed secret references, and do not force-add local configs unless they are intentionally reviewed as tracked artifacts.

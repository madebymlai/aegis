# VectorBT PRO Research Scaffold

This scaffold follows the VectorBT PRO docs around data classes, indicator pipelines, splitters, and `Portfolio.from_signals`. Market data enters the research loop as native VectorBT `Data`; run evidence records the derived strategy, portfolio, metric, and leaderboard artifacts needed to review a strategy idea.

## Flow

```text
data fetch/load
-> component-native strategy/research evidence (`aerd run`)
-> VectorBT PRO portfolio evidence
-> leaderboards and run artifacts
```

## Modules

- `data.py`: native VectorBT market data adapters, feature-panel views, data quality gates, and public metadata safety.
- `data_schema.py`: shared OHLC selection, availability, index identity, and shape helpers.
- `indicators.py`: component-backed indicator execution, feature lineage, and diagnostics.
- `portfolios.py`: owns `vbt.Portfolio.from_signals` execution timing, Open-price validation, and resolved VBT settings.
- `reports.py`: computes portfolio metrics and metric evidence.
- `strategy_runs.py`: component-native optimization orchestration and strategy evidence.
- `run_splits.py`: validates and materializes supported VBT splitter configs for run scoring.
- `split_leaderboard.py`: ranks held-out split evidence for run split scoring.
- `cli.py`: `aerd` dispatcher.

## CLI Contract

Use the single CLI command for local work:

```text
aerd run <config>
```

`aerd run` selects strategy and indicator component IDs directly and writes component strategy/research evidence. Components may expose defaults and `param_space()` callables; Aegis composes them into one native VBT optimization source and centrally scores portfolio metrics.

Both run configs require explicit config paths in v1. Local configs live flat under `research/configs/`; there is no local default experiment workflow and no mode inference from subdirectories.

## Config Contract

YAML is a versioned public contract. Every config must declare `schema_version: 5`. Static config validation runs before any run directory exists. Data-array contract failures discovered from selected components happen before provider data is loaded and mark the run failed with manifest evidence. This in-repo schema v5 contract is forward-first: stale configs that use `lane`, `train`, `model`, `labels`, `label`, `labeler`, `signals`, removed feature-map fields, or invalid split method params are intentionally rejected rather than compatibility-shimmed.

Validation is strict by default:

- Unknown fields fail unless they are inside explicit provider or execution passthrough maps.
- Wrong scalar/list/mapping/null shapes fail without broad coercion.
- Config errors include the offending config path.
- Inline credential-like values are rejected; use environment-backed secret references for provider credentials.
- Inline Python, formulas, import strings, arbitrary script paths, arbitrary notebook paths, run artifact paths, last-run refs, and leaderboard-row refs are rejected from run configs.

Remote provider configs keep scaffold-owned fields first-class (`source`, `symbols`, `start`, `end`, `timeframe`) and put provider-specific VectorBT kwargs behind named passthrough maps. Public artifacts store redacted config evidence only; runtime-expanded secret values are never serialized.

Market data sources are selected from local sources (`synthetic`, `csv`) plus installed VectorBT `*Data` classes. Remote source IDs are derived from the VectorBT class name, for example `YFData` becomes `yf`, `BinanceData` becomes `binance`, and `CCXTData` becomes `ccxt`. Configs cannot import arbitrary provider classes; they can only select providers already exposed by VectorBT. Tests can use a controlled fake-adapter seam to exercise future provider shapes without adding a public import surface.

Configs declare raw data dependencies in `data.arrays`. This field is always a list, even for one entry. `OHLCV` is a shortcut token that expands to `Open`, `High`, `Low`, `Close`, and `Volume`; extra entries must be exact VBT feature names:

```yaml
data:
  source: csv
  path: prices.csv
  symbols: [BTCUSDT]
  arrays: [OHLCV, FundingRate]
```

Run configs do not provide feature or column mapping. Non-standard local columns must be normalized before ingestion or inside a source adapter. CSV input supports flat VBT feature-name columns for one configured symbol and documented MultiIndex layouts that include separate symbol and feature levels, such as `(symbol, feature)` columns. Ambiguous local layouts, missing requested feature columns, and multi-symbol flat CSV input fail at the data boundary instead of guessing.

There is no universal catalog of all possible `data.arrays` values in Aegis. VectorBT exposes feature names per loaded data object through `Data.features` and retrieves them with `Data.get(feature=...)`. Aegis code documents only its shortcut catalog in `research/aegis_research/configuration/schema.py`: `OHLCV_ARRAYS` and `DATA_ARRAY_SHORTCUTS`. All other `data.arrays` entries are exact VBT feature names provided by the selected source.

## Run Config Example

```yaml
schema_version: 5
name: ma_cross_run
output_dir: runs

data:
  source: synthetic
  symbols: [SYN]
  rows: 750
  arrays: [OHLCV]

portfolio:
  entry_budget: 1.0

strategy:
  id: example.ma_cross

indicators:
  - id: example.ma

ranking:
  metric: total_return
  direction: desc
  secondary_metrics: [sharpe_ratio]
```

## Indicator Contract

Run configs use one top-level `indicators` entry per component id. Source selectors and `ids` batching are removed so each component can carry its own `params`, `lock_id`, or `candidate_id` without ambiguity.

Indicator components own reviewed params, selected outputs, defaults, and optional VBT-native param spaces. Component callables receive a market-data bundle and request declared raw features with `data.feature("FeatureName")`, including `data.feature("Close")` for close-only indicators and `data.feature("High")` or `data.feature("Low")` for OHLCV-dependent indicators. Built-in VectorBT-backed components should run through their indicator class `.run(...)` methods with visible params so native outputs preserve effective `window`, `wtype`, and symbol levels.

Trusted custom indicators are added in project code, usually with `vbt.IF(...).with_apply_func(...)`, and then referenced by stable id from config:

```yaml
indicators:
  - id: custom_retvol
```

## Signal And Portfolio Contract

Strategy components emit aligned `entries` and `exits` only. Portfolio sizing, costs, direction, and timing remain config-owned. The runnable v1 portfolio contract is long-only and uses one shared cash pool across all configured symbols.

```yaml
portfolio:
  entry_budget: 1.0
  direction: longonly
```

`portfolio.entry_budget` is required. It states the total portfolio-value share available to executable entry signals on a bar. If two symbols emit executable entries on the same bar with `entry_budget: 0.6`, each receives `0.3` `valuepercent` sizing. Portfolio simulation stays array-based through `vbt.Portfolio.from_signals` with one shared cash pool across all configured symbols.

Strategy runs require Close and Open data so bar-aligned signals can be scored with next-open execution. Missing, misaligned, or null Open prices at required execution rows fail the run instead of falling back to same-close or VBT `NextValidOpen` behavior.

## Native Optimization

For runs that need parameter search, configs declare an `optimization` block and components expose `param_space()` callables whose values are `vbt.Param`. Aegis composes configured strategy and indicator components into one pipeline, wraps it in `vbt.cv_split`, and lets VBT enumerate, select, and evaluate parameter combinations. Aegis does not feed VBT-generated params back into a Python candidate grid.

```yaml
optimization:
  search: random       # or "grid" for exhaustive
  random_subset: 16
  seed: 42
  evidence:
    return_grid: first  # off | first | all
  split:
    method: from_rolling
    params:
      length: 252
      offset: 252
      split: 0.8
    max_splits: 10
```

`optimization.split.method` maps to `vbt.cv_split(splitter=...)` and `optimization.split.params` to `splitter_kwargs`. Set roles are positional: VBT set index 0 is Aegis `selection`, VBT set index 1 is Aegis `held_out`. The selection function maps the configured `ranking.metric` and `ranking.direction` into VBT `selection`, with multi-metric selection handled via `grid_results.xs(metric_name).idxmax()`/`idxmin()`. Tied parameters use `vbt.Param(level=...)`; conditional parameters use `vbt.Param(condition=...)`; `vbt.Param(random_subset=...)` and the top-level `random_subset` interoperate with VBT's lazy-grid behavior. Resource gates (theoretical combinations, sampled combinations, expected result cells, artifact bytes) live on `optimization.preflight` and `optimization.split.max_*` knobs and fail closed before VBT execution. Partial failures (`vbt.NoResult`-only grids, missing metrics, runtime errors) surface as `evidence.optimization.execution_failure` rather than silently shrinking the leaderboard.

`candidate_grid` is removed from the forward run contract. New work must use component `param_space()` callables plus the `optimization` contract; `vbt.Param` jointly searches indicator and strategy parameters inside the composed pipeline.

## Deprecated Run Split Scoring (Scheduled For Removal)

The top-level `split` block is legacy non-optimization scoring shape. Forward configs must use `optimization.split` on the optimization contract. Historical read/reporting code may still understand old artifacts, but new authored configs must not use the candidate-sweep contract.

```yaml
split:
  method: from_rolling
  params:
    length: 252
    offset: 252
    split: 0.8
  max_splits: 100
```

Set roles are positional (set 0 = selection, set 1 = held_out); `set_labels` is rejected by config validation under any `split.params`.

`split.method` must be an exact `vbt.Splitter` constructor method. Use `aerd show splitters from_rolling --json` or another discovered method to inspect signature-derived params and defaults. Compatible methods such as `from_rolling` and `from_purged_kfold` share the same scoring path when VBT returns exactly two non-overlapping sets per split. The first set is used for selection, the second set is used for held-out scoring, and native VBT set labels are preserved in evidence.

## Run Manifest And Artifacts

Every valid run creates its run directory and `manifest.json` before data loading starts. Static config failures still produce no run directory.

The manifest is the machine-readable source of truth for:

- run id, lifecycle status, timestamps, rerun mode, and lineage;
- public redacted config identities and private raw config identity;
- package, platform, Git, VectorBT settings, environment allowlist, and seed evidence;
- stage records and artifact inventory;
- artifact path, schema version, producer stage, content hash, size, status, visibility, and upstream lineage.

Artifact status changes go through recorder/registry transition methods. Completed artifacts are valid evidence only when listed in the manifest with matching hash and size. Temp files, unregistered files, failed artifacts, and orphaned partial native saves are not evidence.

Public artifacts and metadata are redacted. `data.metadata` is written after data loading and public safety checks. Native VectorBT artifacts are private local artifacts by default, version-sensitive, and paired with portable metadata sidecars when persisted.

Successful runs write public-safe config evidence:

- `config.yaml`: redacted resolved config with defaults applied.
- `config_authored.yaml`: redacted authored config view.
- `config_manifest.json`: schema version and raw config identity.

JSON error categories use stable process exits:

| Category | Exit |
|---|---:|
| `invocation` | 2 |
| `config_validation` | 6 |
| `execution_failure` | 10 |
| `interrupted` | 130 |
| `internal_error` | 1 |

The CLI exposes explicit rerun intent with `--rerun-mode` and optional run lineage flags. The default creates a fresh immutable physical run. Overwrite mode creates a new superseding physical run rather than mutating prior evidence in place.

## Components

Components live under `research/components/{indicators,strategies}/`. Discovery reads a top-level literal `COMPONENT_MANIFEST` and `COMPONENT_CALLABLE` without importing the Python file; callable code is loaded only after validation selects that ID. Components can declare `defaults`, optional `param_space_callable`, produced indicator outputs, and consumed strategy outputs. See `docs/examples/components/*_component_example.py`.

Playbooks under `research/playbooks/{indicators,strategies}/` are legacy historical artifacts, not a forward authoring path. See `docs/playbooks.md` for the removal boundary.

Leaderboards rank complete composed strategy candidates, not raw indicators. Component promotion uses persisted candidate rows plus explicit `lock_id` or `candidate_id` refs; manual copying of playbook params is no longer the forward workflow.

## VectorBT PRO Notes

- Use approved `YFData`, `BinanceData`, or `CCXTData` adapters for real fetches once a run needs external data.
- Public portfolio sizing is `portfolio.entry_budget`; the baseline `Portfolio.from_signals` path resolves internal `valuepercent` sizing.
- Portfolio direction is fixed to `longonly` while strategies emit entries and exits.
- Keep high-cardinality parameter sweeps inside VectorBT indicator/portfolio/splitter objects instead of Python loops where possible.
- Use `Portfolio.from_signals` for the first loop; move to `from_order_func` only when signal arrays cannot express the execution model.
- Save only public, non-sensitive run artifacts in git. The `runs/` directory remains ignored except for `.gitkeep`.

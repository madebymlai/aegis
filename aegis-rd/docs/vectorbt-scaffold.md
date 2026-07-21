# VectorBT PRO Research Scaffold

This scaffold follows the VectorBT PRO docs around data classes, indicator pipelines, continuous portfolio replay, and bounds-aware analysis. Market data enters the research loop as native VectorBT `Data`; run evidence records the derived strategy, portfolio, Metric, and Candidate artifacts needed to review a strategy idea. The single multi-asset contract is cross-sectional target allocation; legacy `entries`/`exits` signal flow is no longer a supported authoring path.

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
- `portfolios.py`: owns `vbt.PFO.from_filled_allocations` + `vbt.Portfolio.from_optimizer` execution, terminal liquidation, and resolved VBT settings.
- `reports.py`: computes portfolio metrics and metric evidence.
- `strategy_runs.py`: component-native optimization orchestration and strategy evidence.
- `optimization/continuous_replay.py`: builds each Candidate's single causal full-period Portfolio.
- `optimization/observation_blocks.py`: applies fixed analysis-only ranges to unchanged Portfolios.
- `cli.py`: `aerd` dispatcher.

## CLI Contract

Use the single CLI command for local work:

```text
aerd run <config>
```

`aerd run` selects strategy and indicator component IDs directly and writes component strategy/research evidence. Components may expose defaults and `param_space()` callables; Aegis composes them into one native VBT optimization source and centrally scores portfolio metrics.

Both run configs require explicit config paths in v1. Local configs live flat under `research/configs/`; there is no local default experiment workflow and no mode inference from subdirectories.

## Config Contract

YAML is a versioned public contract. Every config must declare `schema_version: 6`. Static config validation runs before any run directory exists. Data-array contract failures discovered from selected components happen before provider data is loaded and mark the run failed with manifest evidence. This in-repo schema v6 contract is forward-first: stale configs that use `lane`, `train`, `model`, `labels`, `label`, `labeler`, `signals`, removed feature-map fields, source selectors, indicator `ids`, `candidate_grid`, top-level `split`, or invalid split method params are intentionally rejected rather than compatibility-shimmed.

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
schema_version: 6
name: ma_cross_run
output_dir: runs

data:
  source: synthetic
  symbols: [SYN]
  rows: 750
  arrays: [OHLCV]

portfolio:
  target_exposure_cap: 1.0

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

Run configs use one top-level `indicators` entry per component id: one indicator entry per component id. Source selectors and `ids` batching are removed so each component can carry its own `params`, `lock_id`, or `candidate_id` without ambiguity. Direct `candidate_id` pins include the source `run_id` so repeat runs with the same candidate key remain unambiguous.

Indicator components own reviewed params, selected outputs, defaults, and optional VBT-native param spaces. Component callables receive a market-data bundle and request declared raw features with `data.feature("FeatureName")`, including `data.feature("Close")` for close-only indicators and `data.feature("High")` or `data.feature("Low")` for OHLCV-dependent indicators. Built-in VectorBT-backed components should run through their indicator class `.run(...)` methods with visible params so native outputs preserve effective `window`, `wtype`, and symbol levels.

Trusted custom indicators are added in project code, usually with `vbt.IF(...).with_apply_func(...)`, and then referenced by stable id from config:

```yaml
indicators:
  - id: custom_retvol
```

## Allocation And Portfolio Contract

Strategy components emit exactly one declared allocation-native frame from `{active, scores, ranks, target_weights}` (the registered `STRATEGY_ALLOCATION_OUTPUTS`). Manifests declare the shape via a singular `output_name: str`. Selection convention: non-NaN cells = selected this rebalance row; NaN = excluded. Top-N filtering is owned by the component.

Portfolio policy (`research/aegis_research/portfolio_policy/`) owns the conversion from the declared shape to a validated allocations frame: it applies the executable mask, normalizes against `portfolio.target_exposure_cap`, and writes the terminal-liquidation row. Costs, direction, and timing remain config-owned. Each Candidate uses one shared cash pool across all configured symbols.

```yaml
portfolio:
  target_exposure_cap: 1.0
  direction: longonly
```

`portfolio.target_exposure_cap` is required and is the gross allocation cap in units of portfolio value (e.g. `0.8` reserves 20% in cash). It replaces the removed `portfolio.entry_budget` knob. Validated allocations are summed across symbols per row and rescaled so the row gross does not exceed the cap; the policy frame is then passed straight to the substrate.

The portfolio substrate is fixed for v1:

- Construction: `vbt.PFO.from_filled_allocations(allocations)` followed by `vbt.Portfolio.from_optimizer(pfo, close=close, ...)`.
- `size_type="targetpercent"` — cells are interpreted as target weights of group value.
- `pf_method="from_signals"` — target allocations flow through the pinned signal engine.
- `direction` — supplied by validated portfolio config and shared by every Candidate.
- `call_seq="auto"` — frozen for v1; sell-before-buy within the shared-cash group.
- `cash_sharing=True` with `group_by={True | vbt.ExceptLevel(SYMBOL_LEVEL)}` — single-candidate runs group across all symbols; multi-candidate sweeps group across symbols within each candidate.
- `price="nextopen" | "nextclose"` — configured fills are delayed by one bar.

`target_weights[t] = 0` requests closure using the configured next-bar fill timing. `next_open` requires Open data; `next_close` fills from Close data.

Terminal liquidation is the single forward path: the policy explicitly sets `allocations.iloc[-1] = 0.0` so any position held into the terminal bar closes at the terminal bar's close, producing a cash-realized terminal (no mark-to-market phantom). This mirrors the maintainer's blessed pattern for `Portfolio.from_optimizer` — see `docs/solutions/best-practices/vectorbt-close-optimizer-positions-at-end-2026-05-17.md`.

Both supported fill modes apply an effective one-bar delay, so the continuous replay never executes a decision on the same bar that produced it.

For the contract's full historical motivation, see `docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md` and the implementation plan at `docs/plans/2026-05-22-003-feat-portfolio-target-allocation-pfo-contract-plan.md`.

## Native Optimization

For runs that need parameter search, configs declare an `optimization` block and components expose `param_space()` callables whose values are `vbt.Param`. Aegis composes configured Strategy and Indicator Components, materializes the exact grid or deterministic random sample, derives one common Warmup from all sampled lookbacks, and replays every Candidate continuously over the same Development Period.

```yaml
optimization:
  search: random       # or "grid" for exhaustive
  random_subset: 16
  seed: 42
  observation_block_bars: 252
```

`optimization.observation_block_bars` partitions only the scored Development interval into labeled, half-open observational ranges. Aegis creates every Portfolio before block analysis and never slices allocations or constructs a Portfolio per range. Internally, the fixed `vbt.Splitter.from_splits` + `Splitter.apply` path carries resolved bounds to Metric extractors over the unchanged full Portfolio. The Portfolio itself is never `vbt.Takeable`.

The ranking Metric is ranked within each Observation Block using its registered direction. A Candidate's selection score is its mean within-block rank; equal scores break by materialized Candidate position. Complete-period Metrics remain descriptive Evidence. Random optimization requires a seed so the materialized sample and Evidence are deterministic. Partial failures (`vbt.NoResult`, missing Metrics, runtime errors) surface as execution failure Evidence rather than silently shrinking the comparison.

`candidate_grid` is unknown to the forward schema. New work must use component `param_space()` callables plus the `optimization` contract; `vbt.Param` jointly searches indicator and strategy parameters inside the composed pipeline.

## Retired Public Split Scoring

The top-level `split` block, `optimization.split`, arbitrary Splitter method selection, `aerd show splitters`, Selection/Held-out sweeps, and terminal Held-out replay are retired contract surface. Forward configs use only continuous replay plus `optimization.observation_block_bars`. The remaining internal VBT Splitter represents already-resolved Observation Block bounds for analysis; it cannot alter execution or Portfolio state.

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

Components live under `research/components/{indicators,strategies}/`. Discovery reads a top-level literal `COMPONENT_MANIFEST`, the required module-level `run` entry point, and optional module-level `param_space` without importing the Python file; callable code is loaded only after validation selects that ID. Components can declare defaults, produced indicator outputs, and consumed strategy outputs. See `research/aegis_research/component_registry/indicator_example.py` and `research/aegis_research/component_registry/strategy_example.py` (packaged examples round-tripped through the real registry parser).

Playbooks are no longer a forward authoring path. See `docs/playbooks.md` for the removal boundary.

Leaderboards rank complete composed strategy candidates, not raw indicators. Component locks use persisted candidate rows plus explicit `lock_id` or `candidate_id` plus source `run_id` refs; manual copying of playbook params is no longer the forward workflow.

## VectorBT PRO Notes

- Use approved `YFData`, `BinanceData`, or `CCXTData` adapters for real fetches once a run needs external data.
- Public portfolio sizing is `portfolio.target_exposure_cap` (gross cap, units of portfolio value); the substrate is `vbt.PFO.from_filled_allocations` + `vbt.Portfolio.from_optimizer` with `size_type="targetpercent"` and `pf_method="from_signals"`.
- Portfolio direction and next-bar fill timing are validated config. Strategies emit one allocation-native frame; the policy layer produces the validated `targetpercent` allocations.
- Materialize high-cardinality Candidate batches once, replay each path continuously, and use VBT Splitter only to apply analysis-only Observation Block bounds.
- Stay on the `PFO.from_filled_allocations` + `Portfolio.from_optimizer` path for the first loop; reach for `from_order_func` only when target allocations cannot express the execution model.
- Save only public, non-sensitive run artifacts in git. The `runs/` directory remains ignored except for `.gitkeep`.

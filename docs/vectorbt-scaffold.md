# VectorBT PRO Research Scaffold

This scaffold follows the VectorBT PRO docs around data classes, indicator pipelines, labels, splitters, and `Portfolio.from_signals`. Market data enters the research loop as native VectorBT `Data`; Pandas frames are explicit derived views for sklearn-ready stages and portable artifacts.

## Flow

```text
data fetch/load
-> indicator matrix
-> forward labels
-> train/export model
-> probability-to-signal rules
-> VectorBT PRO portfolio simulation
-> survival report
```

## Modules

- `data.py`: native VectorBT market data adapters, feature-panel views, data quality gates, and public metadata safety.
- `data_schema.py`: shared OHLC selection, availability, index identity, and shape helpers.
- `indicators.py`: reusable indicator builders using VectorBT PRO indicators.
- `labels.py`: VectorBT PRO `FIXLB`, `TRENDLB`, and `PIVOTLB` label wrappers.
- `models.py`: training and `joblib` export boundary.
- `signals.py`: converts model probabilities into entries and exits.
- `portfolios.py`: owns `vbt.Portfolio.from_signals` assumptions.
- `validation.py`: evaluates train/test validation flows and keeps split mechanics out of orchestration.
- `splits.py`: builds holdout or `vbt.Splitter` rolling validation splits.
- `reports.py`: turns IS/OOS portfolio stats into a blunt survival verdict.
- `experiments.py`: config-driven orchestration.
- `cli.py`: one-command runner.

## Run

```bash
python -m research.aegis_research.cli run research/configs/experiments/synthetic_ml_baseline.yaml
```

The default config uses deterministic synthetic OHLCV data, so it is safe for CI and does not require exchange credentials.

## Config Contract

Experiment YAML is a versioned public contract. Every config must declare `schema_version: 1` and is validated before any run directory, data fetch, model training, portfolio simulation, report generation, or artifact write.

Validation is strict by default:

- Unknown fields fail unless they are inside explicit provider or execution passthrough maps.
- Wrong scalar/list/mapping/null shapes fail without broad coercion.
- Config errors include the offending config path.
- Inline credential-like values are rejected; use environment-backed secret references for provider credentials.

Remote provider configs keep scaffold-owned fields first-class (`source`, `symbols`, `start`, `end`, `timeframe`) and put provider-specific VectorBT kwargs behind named passthrough maps. Public artifacts store redacted config evidence only; runtime-expanded secret values are never serialized.

Market data sources are selected from the approved in-code adapter registry: `synthetic`, `csv`, `yfinance`, `binance`, and `ccxt`. Configs cannot import arbitrary provider classes. Tests can use a controlled fake-adapter seam to exercise future provider shapes without adding a public import surface.

Provider-native symbols are passed through as authored in `data.symbols`. The scaffold does not normalize tickers, exchange symbols, or aliases in schema v1 because hidden normalization would make evidence hard to audit.

Use `data.feature_map` when a source uses non-standard OHLCV feature names. The map uses logical scaffold keys and source feature names:

```yaml
data:
  source: csv
  path: prices.csv
  symbols: [BTCUSDT]
  feature_map:
    close: close_price
    volume: base_volume
```

CSV input supports flat OHLCV columns for one configured symbol and documented MultiIndex layouts that include separate symbol and feature levels, such as `(symbol, feature)` columns. Ambiguous local layouts, missing mapped source columns, and multi-symbol flat CSV input fail at the data boundary instead of guessing.

## Native Data Lifecycle

Every source returns a `MarketDataResult` with native `vbt.Data`, safe metadata, asset diagnostics, quality state, and known-secret evidence. Derived feature views are requested with `result.feature("Close")` or the OHLC helpers and always return timestamp-by-symbol DataFrames. Orchestration does not select a first symbol or squeeze single-symbol panels.

Required OHLCV features are derived from the experiment config. `fixlb` needs close only. `trendlb` and `pivotlb` need close, high, and low. Open and volume are optional until a stage explicitly requires them.

Quality states are fail-fast:

| State | Meaning | Downstream allowed |
|---|---|---|
| `healthy` | Required symbols, features, index evidence, coverage, and numeric checks pass. Optional missing OHLCV features may appear as warnings. | Yes |
| `degraded_allowed` | A named degradation such as `missing_rows`, `duplicate_index`, `non_monotonic_index`, or `skipped_symbols` was explicitly allowed by `data.quality.allowed_degradations`. | Yes |
| `rejected` | Loaded data violates required feature, symbol, missingness, index, or numeric requirements without an explicit policy. | No |
| `provider_failed` | A provider adapter failed before usable native data was available. The error is redacted into public-safe metadata. | No |

`skip_on_error` defaults to `false`. If provider partial fetch behavior is needed, set both `data.skip_on_error: true` and `data.quality.allowed_degradations: [skipped_symbols]`; otherwise skipped configured symbols are rejected.

Cache and update behavior is metadata-only in schema v1. Public metadata records update support and uses `cache_policy: disabled_in_schema_v1`; cache paths, sessions, clients, proxies, and private transport objects remain denied passthrough fields.

## Run Manifest And Artifacts

Every valid run creates its run directory and `manifest.json` before data loading or model work starts. Static config failures still produce no run directory.

The manifest is the machine-readable source of truth for:

- run id, lifecycle status, timestamps, rerun mode, and lineage;
- public redacted config identities and private raw config identity;
- package, platform, Git, VectorBT settings, environment allowlist, and seed evidence;
- stage records and artifact inventory;
- artifact path, schema version, producer stage, content hash, size, status, visibility, and upstream lineage.

Artifact status changes go through recorder/registry transition methods. Completed artifacts are valid evidence only when listed in the manifest with matching hash and size. Temp files, unregistered files, failed artifacts, and orphaned partial native saves are not evidence.

Public artifacts and metadata are redacted. `data.metadata` is written after data loading and public safety checks, before downstream modeling and before private native persistence. Data-quality failures keep the public metadata artifact and fail the run before writing `data.native`.

Native VectorBT artifacts are private local artifacts by default, version-sensitive, and paired with portable metadata sidecars so manifest validation does not require loading pickles. Unsafe private native persistence fails the run closed after safe public metadata has been recorded.

The CLI exposes explicit rerun intent with `--rerun-mode` and optional run lineage flags. The default creates a fresh immutable physical run. Overwrite mode creates a new superseding physical run rather than mutating prior evidence in place.

## Validation Modes

Use a single chronological holdout:

```yaml
split:
  kind: holdout
  train_size: 0.7
  embargo_bars: 5
```

Use VectorBT PRO rolling windows through `vbt.Splitter.from_n_rolling`:

```yaml
split:
  kind: rolling
  train_size: 0.7
  embargo_bars: 5
  n: 5
  length: optimize
```

Holdout is represented as one split. Rolling validation writes one child artifact set per split: model, train/test probabilities, train/test signals, train/test portfolio artifacts, train/test metrics, and metadata. Aggregate probability/signal/metric/report artifacts link back to those child artifacts. There is no generic top-level `artifacts/model.joblib` for split validation because it would imply deployment readiness.

## Label Modes

Use VectorBT PRO `FIXLB` fixed look-ahead labels:

```yaml
labels:
  kind: fixlb
  horizon: 5
  threshold: 0.0
```

Use VectorBT PRO `TRENDLB` trend labels:

```yaml
labels:
  kind: trendlb
  up_th: 0.08
  down_th: 0.08
  mode: binary
  positive_value: 1
```

Use VectorBT PRO `PIVOTLB` pivot labels:

```yaml
labels:
  kind: pivotlb
  up_th: 0.08
  down_th: 0.08
  positive_value: -1
```

## VectorBT PRO Notes

- Use approved `YFData`, `BinanceData`, or `CCXTData` adapters for real fetches once an experiment needs external data.
- For schema v1, `Portfolio.from_signals` sizing accepts `amount`, `value`, `percent`, `percent100`, `valuepercent`, and `valuepercent100`; target size types are intentionally rejected.
- Portfolio direction accepts `longonly`, `shortonly`, and `both`.
- TRENDLB remains binary-only in schema v1 because the scaffold trains binary classification targets.
- Keep high-cardinality parameter sweeps inside VectorBT indicator/portfolio/splitter objects instead of Python loops where possible.
- Use `Portfolio.from_signals` for the first loop; move to `from_order_func` only when signal arrays cannot express the execution model.
- Save only public, non-sensitive run artifacts in git. The `runs/` directory remains ignored except for `.gitkeep`.

## Report Frequency

Survival report gates that depend on annualized metrics require explicit frequency assumptions:

```yaml
report:
  freq: 1D
  year_freq: 252D
  min_oos_sharpe: 0.5
```

The scaffold does not infer annualization solely from `data.timeframe`; report frequency is part of the experiment contract.

## Run Config Artifacts

Successful runs write public-safe config evidence:

- `config.yaml`: redacted resolved config with defaults applied.
- `config_authored.yaml`: redacted authored config view.
- `config_manifest.json`: schema version and raw config identity.

Invalid static configs fail before run artifact creation. Data-contract failures that require loaded data may happen after data access; public `data.metadata` is still recorded when it passes safety validation, and downstream/native artifacts are not written.

The root manifest registers these config artifacts with hashes and schema versions; `config_manifest.json` is generated evidence, not a parallel source of truth.

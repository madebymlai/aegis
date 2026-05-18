# VectorBT PRO Research Scaffold

This scaffold follows the VectorBT PRO docs around data classes, indicator pipelines, labels, splitters, and `Portfolio.from_signals`. Market data enters the research loop as native VectorBT `Data`; Pandas frames are explicit derived views for sklearn-ready stages and portable artifacts.

## Flow

```text
data fetch/load
-> strategy/research sweep over playbooks or components (`aerd run`)
-> ML model-plugin training (`aerd run --train`)
-> VectorBT PRO portfolio evidence
-> reports and leaderboards
```

## Modules

- `data.py`: native VectorBT market data adapters, feature-panel views, data quality gates, and public metadata safety.
- `data_schema.py`: shared OHLC selection, availability, index identity, and shape helpers.
- `indicator_registry.py`: project-owned built-in, primitive, and trusted custom indicator definitions.
- `indicators.py`: VectorBT-native indicator stage, model-feature boundary, lineage, and diagnostics.
- `labels.py`: VectorBT PRO `FIXLB`, `TRENDLB`, and `PIVOTLB` label wrappers.
- `models.py`: training and `joblib` export boundary.
- `signals.py`: converts `positive_class_probability` panels into long-only raw threshold-state entries/exits plus compact diagnostics.
- `portfolios.py`: owns `vbt.Portfolio.from_signals` execution timing, Open-price validation, and resolved VBT settings.
- `validation.py`: evaluates train/test validation flows and keeps split mechanics out of orchestration.
- `splits.py`: builds VectorBT purged K-fold validation splits.
- `reports.py`: turns IS/OOS portfolio stats into a blunt survival verdict.
- `strategy_runs.py`: playbook-backed and component-backed strategy-sweep orchestration.
- `training.py` and `experiments.py`: ML model-plugin training orchestration.
- `cli.py`: mode-aware `aerd` dispatcher.

## Run Modes

Use `docs/examples/scaffold_experiment_walkthrough.ipynb` for the public runnable training walkthrough. It uses deterministic synthetic OHLCV data, an inline config, and explicit model registry setup, so it is safe for learning the scaffold and does not require exchange credentials.

Use the single CLI command for local work:

```text
aerd run <strategy-run-config>
aerd run --train <config>
```

Default `aerd run` selects strategy and indicator component/playbook IDs by explicit source refs and writes source-labeled strategy/research sweep evidence. `aerd run --train` owns ML model-plugin training through the config's `train:` section; model-shaped configs passed to default `aerd run` fail with guidance to use `aerd run --train`.

The walkthrough is scaffold evidence only. It is not validated trading methodology, empirical edge, or investment advice.

## Config Contract

YAML is a versioned public contract. Every config must declare `schema_version: 2` and is validated before any run directory, data fetch, model training, portfolio simulation, report generation, or artifact write. Mode is selected by the CLI (`aerd run` or `aerd run --train`), not by config subdirectories or a top-level lane field. This in-repo schema v2 contract is forward-first: older draft v2 configs that used non-purged split kinds are intentionally rejected rather than compatibility-shimmed.

Validation is strict by default:

- Unknown fields fail unless they are inside explicit provider or execution passthrough maps.
- Wrong scalar/list/mapping/null shapes fail without broad coercion.
- Config errors include the offending config path.
- Inline credential-like values are rejected; use environment-backed secret references for provider credentials.
- Inline Python, formulas, import strings, arbitrary script paths, arbitrary notebook paths, run artifact paths, last-run refs, and leaderboard-row refs are rejected from run configs.

Remote provider configs keep scaffold-owned fields first-class (`source`, `symbols`, `start`, `end`, `timeframe`) and put provider-specific VectorBT kwargs behind named passthrough maps. Public artifacts store redacted config evidence only; runtime-expanded secret values are never serialized.

Market data sources are selected from local sources (`synthetic`, `csv`) plus installed VectorBT `*Data` classes. Remote source IDs are derived from the VectorBT class name, for example `YFData` becomes `yf`, `BinanceData` becomes `binance`, and `CCXTData` becomes `ccxt`. Configs cannot import arbitrary provider classes; they can only select providers already exposed by VectorBT. Tests can use a controlled fake-adapter seam to exercise future provider shapes without adding a public import surface.

Provider-native symbols are passed through as authored in `data.symbols`. The scaffold does not normalize tickers, exchange symbols, or aliases in schema v2 because hidden normalization would make evidence hard to audit.

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

## Indicator Contract

Train-mode configs reference project registry ids for built-in indicators inside `train.indicators`. Strategy/research `run` configs use explicit `source: component` or `source: playbook` refs for strategies and indicators, including component `id: all` selection for indicators. They do not define inline formulas, imports, Python snippets, arbitrary functions, or arbitrary notebook paths. `aerd run --train` requires `train.label` and `train.model`; model refs keep `source`, but v1 accepts only `source: plugin`.

```yaml
indicators:
  invalid_value_policy: drop_rows
  specs:
    - id: returns
      params:
        window: [1, 5, 20]
      outputs: [returns]
      model_features:
        - output: returns

    - id: ma
      params:
        window: [10, 30]
        wtype: simple
      grid: zipped
      outputs: [ma]
      model_features:
        - output: ma
          transform: distance_to_close

    - id: rsi
      params:
        window: [14]
        wtype: wilder
      outputs: [rsi]
      model_features:
        - output: rsi
          transform: scale_0_1
```

Built-in VectorBT indicators run through their indicator class `.run(...)` methods with visible params. MA and RSI preserve effective `window` and `wtype` levels in native outputs by using visible parameter settings rather than hiding params. Ordinary sweeps use parameter lists. Zipped lists are the default. Cartesian products require both `grid: product` and `param_product: true` so grid expansion is explicit in config and metadata.

Primitive features such as returns and rolling volatility stay local in schema v2, but they still produce the same lineage, feature mapping, invalid-value diagnostics, and artifact metadata as VectorBT-backed indicators. Reusable/domain transforms should graduate to a reviewed registry definition when they need first-class indicator identity or repeated use.

Trusted custom indicators are added in project code, usually with `vbt.IF(...).with_apply_func(...)`, and then referenced by stable id from config:

```yaml
indicators:
  specs:
    - id: custom_retvol
      params:
        window: [5]
      outputs: [retvol]
      model_features:
        - output: retvol
```

Custom `IndicatorFactory` outputs must be bar-aligned in schema v2: each selected output preserves the input index and symbol shape. Shape-changing transforms such as Renko bricks, event lists, compressed bars, trades, or arbitrary objects belong in a separate future pipeline, such as a `vbt.parameterized` workflow, not the experiment indicator stage.

The indicator stage keeps native VectorBT objects private until the modeling boundary. Public artifacts write portable `indicators.metadata`, `indicators.lineage`, `indicators.diagnostics`, and `indicators.features.schema`. Private native indicator objects and native outputs are stored as `indicators.native` with a public metadata sidecar. sklearn receives only the derived model-feature matrix with deterministic feature names and reversible mapping; native VectorBT objects never enter sklearn internals.

## Native Data Lifecycle

Every source returns a `MarketDataResult` with native `vbt.Data`, safe metadata, asset diagnostics, quality state, and known-secret evidence. Derived feature views are requested with `result.feature("Close")` or the OHLC helpers and always return timestamp-by-symbol DataFrames. Orchestration does not select a first symbol or squeeze single-symbol panels.

Required OHLCV features are derived from the experiment config. `fixlb` needs close only. `trendlb` and `pivotlb` need close, high, and low. The default signal timing `next_open` also requires Open; explicit `same_close` is the only v1 timing override that allows close-only data. Volume is optional until a stage explicitly requires it.

## Signal And Portfolio Contract

The runnable v1 signal contract is long-only. Model plugins emit `positive_class_probability`; the signal stage interprets that probability only as evidence for entering or exiting a long position. It does not derive shorts, reversals, bearish leverage, or `direction: both` behavior from one positive-class score.

```yaml
signals:
  policy: long_only_hysteresis
  long_entry_threshold: 0.55
  long_exit_threshold: 0.50
  execution_timing: next_open

portfolio:
  entry_budget: 1.0
  direction: longonly
```

`portfolio.entry_budget` is required. It states the total portfolio-value share available to executable entry signals on a bar. If two symbols emit executable entries on the same bar with `entry_budget: 0.6`, each receives `0.3` `valuepercent` sizing. Raw signals that cannot execute in the current split, such as terminal `next_open` signals or market-index gap signals, remain diagnostic evidence but receive no generated size.

`long_only_hysteresis` uses strict threshold comparisons. A probability greater than `long_entry_threshold` emits a raw entry state. A probability less than `long_exit_threshold` emits a raw exit state. Equality with either threshold is part of the hold band and emits no raw signal. Legacy `signals.long_threshold` and `signals.exit_threshold` are rejected so configs must state the action-specific fields.

Raw signal CSVs are threshold-state evidence, not order evidence. Repeated high probabilities can produce repeated raw entry states while VBT ignores redundant entries when already in position. Public signal diagnostics record raw counts, missing probability counts, simultaneous raw state counts, cleaned diagnostic event-chain counts, policy metadata, threshold values, source probability metadata, split/set/symbol identity, and the selected execution timing. Cleaned diagnostics are review evidence only; portfolio simulation still receives the raw entry/exit panels.

Default portfolio execution uses `price="nextopen"` with an aligned Open panel and does not manually shift signals. If `next_open` is selected and Open is unavailable, missing, misaligned, or null at required execution rows, the run fails instead of falling back to same-close or VBT `NextValidOpen` behavior. A raw signal on the last bar of a train/test split has no following in-split Open; it remains in raw diagnostics and increments terminal non-executable counts rather than borrowing a row from another split.

The only accepted v1 timing modes are `next_open` and explicit `same_close`. `same_close` records the research override and does not require Open. `next_close`, custom timing modes, and valid-price skipping are deferred until separate contracts pin their artifact semantics.

Portfolio simulation stays array-based through `vbt.Portfolio.from_signals`. The scaffold generates the `valuepercent` size panel internally from executable entry states, uses one shared cash pool across all configured symbols with `cash_sharing=True` and `group_by=True`, and applies `call_seq="auto"` so sells can be ordered before buys inside the shared group. This is still event-style signal execution: entries open exposure and exits close exposure; existing positions are not automatically resized into equal weights, ranked top-N allocations, or target weights. VectorBT automatic call sequencing uses predetermined prices and is not a custom path-dependent execution engine. Public portfolio diagnostics record these sizing, grouping, timing, cost, order-count, trade-count, and caveat fields. Private native portfolios remain local artifacts with public metadata sidecars; reviewers should be able to audit the signal/portfolio contract from public JSON and CSV artifacts without loading VBT pickles.

Quality states are fail-fast:

| State | Meaning | Downstream allowed |
|---|---|---|
| `healthy` | Required symbols, features, index evidence, coverage, and numeric checks pass. Optional missing OHLCV features may appear as warnings. | Yes |
| `degraded_allowed` | A named degradation such as `missing_rows`, `duplicate_index`, `non_monotonic_index`, or `skipped_symbols` was explicitly allowed by `data.quality.allowed_degradations`. | Yes |
| `rejected` | Loaded data violates required feature, symbol, missingness, index, or numeric requirements without an explicit policy. | No |
| `provider_failed` | A provider adapter failed before usable native data was available. The error is redacted into public-safe metadata. | No |

`skip_on_error` defaults to `false`. If provider partial fetch behavior is needed, set both `data.skip_on_error: true` and `data.quality.allowed_degradations: [skipped_symbols]`; otherwise skipped configured symbols are rejected.

Cache and update behavior is metadata-only in schema v2. Public metadata records update support and uses `cache_policy: disabled_in_schema_v2`; cache paths, sessions, clients, proxies, and private transport objects remain denied passthrough fields.

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

The canonical CLI is `aerd`. Use `aerd run <config>` for playbook-backed or component-backed strategy/research sweeps, and `aerd run --train <config>` for model-plugin training. Use `--json` for agent/CI automation; successful JSON is written to stdout, structured errors are written to stderr, and run manifests remain the detailed artifact inventory.

Both run modes require explicit config paths in v1. Local configs live flat under `research/configs/`; there is no local default experiment workflow and no mode inference from subdirectories.

Completed survival verdicts are research outcomes, not process failures. A completed `rejected` or `needs_more_evidence` report still exits `0`; automation should parse the JSON report status when it needs verdict gating.

JSON error categories use stable process exits:

| Category | Exit |
|---|---:|
| `invocation` | 2 |
| `config_validation` | 6 |
| `execution_failure` | 10 |
| `interrupted` | 130 |
| `internal_error` | 1 |

The CLI exposes explicit rerun intent with `--rerun-mode` and optional run lineage flags. The default creates a fresh immutable physical run. Overwrite mode creates a new superseding physical run rather than mutating prior evidence in place.

## Components And Playbooks

Promoted components live under `research/components/{labels,indicators,strategies}/`. Discovery reads a top-level literal `COMPONENT_MANIFEST` and `COMPONENT_CALLABLE` without importing the Python file; callable code is loaded only after lane validation selects that ID. Local component files are ignored by git except each placeholder README. See `docs/components.md` and `docs/examples/components/*_component_example.py`.

Notebook playbooks live under `research/playbooks/{labels,indicators,strategies}/` and are selected by stable ID from notebook metadata, not by path. Indicator playbook IDs represent one indicator idea/family; parameter sweeps inside that family are allowed, and a baseline may name exactly one component indicator ID. See `docs/playbooks.md` and `docs/examples/playbooks/*_playbook_example.ipynb`.

## Validation Modes

Schema v2 supports one experiment validation mode: VectorBT PRO purged K-fold with one test fold per split. Chronological holdout, ordinary rolling validation, and overlapping CPCV-style test-fold combinations are not exposed because all current label generators are look-ahead targets, and duplicated or unpurged look-ahead metrics are not written as survival evidence.

Use purged K-fold as the decision-grade path for supervised look-ahead labels when exact label evaluation times are available:

```yaml
split:
  kind: purged_kfold
  n_folds: 5
  n_test_folds: 1
  purge_td: 0D
  embargo_td: 0D
  max_splits: 5
  max_estimated_output_cells: 500000
  max_public_artifact_bytes: 5000000
```

Purged validation passes explicit prediction and evaluation time `Series` into `vbt.Splitter.from_purged_kfold`. `purge_td` is added to evaluation times when purging overlapping training samples; `embargo_td` excludes training predictions too close after the latest test evaluation time. Neither setting replaces concrete label evaluation times.

Decision-grade in this scaffold means label-window purging and split/set identity were proven. It does not certify feature causality, portfolio execution timing, or strategy profitability. The report records `decision_grade_scope: label_window_purging`, keeps feature causality marked unchecked, and treats current aggregate metrics as descriptive summaries; per-split test metrics remain the decision evidence. Portfolio headline metrics are shared-cash group metrics, not means of independent per-symbol portfolios, and metrics artifacts record `freq`, `year_freq`, benchmark status, and metric scope.

Purged validation writes one child artifact set per split: model, train/test probabilities, train/test raw threshold-state signals, train/test signal diagnostics, train/test portfolio diagnostics, private train/test portfolio artifacts, train/test metrics, and metadata. Aggregate probability, raw signal, signal diagnostic, portfolio diagnostic, metric, and report artifacts link back to those child artifacts. There is no generic top-level `artifacts/model.joblib` for split validation because it would imply deployment readiness.

## Label Modes

Use VectorBT PRO `FIXLB` fixed look-ahead labels:

```yaml
labels:
  generator:
    kind: fixlb
    params:
      n: 5
  target:
    role: supervised_target
    source_output: labels
    select:
      params:
        n: 5
    transform:
      name: threshold_future_return
      version: 1
      params:
        threshold: 0.0
```

The lower-level label builder can preserve VectorBT PRO `TRENDLB` trend labels, but schema v2 experiment configs reject them until a confirmation-time oracle provides exact evaluation times:

```yaml
labels:
  generator:
    kind: trendlb
    params:
      up_th: 0.08
      down_th: 0.08
      mode: binary
  target:
    role: supervised_target
    source_output: labels
    select:
      params:
        up_th: 0.08
        down_th: 0.08
        mode: binary
    transform:
      name: identity_binary
      version: 1
      params:
        positive_value: 1
```

The lower-level label builder can preserve VectorBT PRO `PIVOTLB` pivot labels, but schema v2 experiment configs reject them until a confirmation-time oracle provides exact evaluation times:

```yaml
labels:
  generator:
    kind: pivotlb
    params:
      up_th: 0.08
      down_th: 0.08
  target:
    role: supervised_target
    source_output: labels
    transform:
      name: positive_event
      version: 1
      params:
        positive_value: -1
```

Label generation is native-first. Runs preserve the native VectorBT object and raw `.labels` separately from the selected model target. The current runnable experiment path accepts only `FIXLB` with `role: supervised_target` binary classification targets; continuous `TRENDLB` modes, sparse-event targets, and regime targets are lower-level label-builder capabilities that require future estimator support in #9 and confirmation-time oracle support before training.

Label functions use future information and are target generators, not predictor features. `FIXLB` fixed-horizon labels can produce exact evaluation times from the actual future row timestamps, including irregular datetime indexes. `TRENDLB` and `PIVOTLB` remain fail-closed for decision-grade validation unless a confirmation-time oracle proves when each historical label became knowable; label-value parity alone is not enough because VectorBT pivot/trend labels are written on historical rows using future confirmation.

Configs that request non-purged split kinds fail at config validation. Purged runs write public `labels.evaluation_evidence` and `splits.evidence` artifacts with exact train/test membership, row-level prediction/evaluation intervals, no-leakage invariant status, resource estimates, and actual public artifact byte-cap enforcement. Private native VectorBT splitters are persisted only as replay/debug sidecars; reviewers should not need to unpickle them to audit decision-grade status.

## VectorBT PRO Notes

- Use approved `YFData`, `BinanceData`, or `CCXTData` adapters for real fetches once an experiment needs external data.
- For schema v2, public portfolio sizing is `portfolio.entry_budget`; the baseline `Portfolio.from_signals` path resolves internal `valuepercent` sizing. Public `size`, `size_type`, and target-allocation sizing are rejected until a separate allocation-mode contract exists.
- Portfolio direction is fixed to `longonly` in schema v2 while signals consume only `positive_class_probability`; `shortonly` and `both` are rejected until a future side-specific signal contract exists.
- `TRENDLB` config accepts `binary`, `binary_cont`, `binary_cont_sat`, `pct_change`, and `pct_change_norm`; only `binary` is compatible with the current binary classifier target path.
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

Label and split evidence artifacts are also public and manifest-linked:

- `labels/evaluation_evidence.json`: selected-target prediction/evaluation times by row and symbol.
- `splits/evidence.json`: split/set membership, source-index identity, purging settings, row-level intervals for purged runs, and leakage-invariant status.

Invalid static configs fail before run artifact creation. Data-contract failures that require loaded data may happen after data access; public `data.metadata` is still recorded when it passes safety validation, and downstream/native artifacts are not written.

The root manifest registers these config artifacts with hashes and schema versions; `config_manifest.json` is generated evidence, not a parallel source of truth.

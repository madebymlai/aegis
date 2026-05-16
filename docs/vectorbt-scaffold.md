# VectorBT PRO Research Scaffold

This scaffold follows the VectorBT PRO docs around data classes, indicator pipelines, labels, splitters, and `Portfolio.from_signals`.

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

- `data.py`: local, synthetic, and VectorBT PRO remote data adapters.
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

Rolling validation writes per-split train/test metrics to `split_metrics.csv` and aggregates test metrics into the survival report.

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

- Use `YFData`, `BinanceData`, or `CCXTData` for real fetches once an experiment needs external data.
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

Invalid static configs fail before run artifact creation. Data-contract failures that require loaded data may happen after data access, but must not write public artifacts.

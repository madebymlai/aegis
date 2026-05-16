# VectorBT PRO Research Scaffold

This scaffold follows the VectorBT PRO docs around data classes, indicator pipelines, labels, splitters, and `Portfolio.from_signals`.

## Flow

```text
data fetch/load
-> factor matrix
-> forward labels
-> train/export model
-> probability-to-signal rules
-> VectorBT PRO portfolio simulation
-> survival report
```

## Modules

- `data.py`: local, synthetic, and VectorBT PRO remote data adapters.
- `indicators.py`: reusable indicator builders using VectorBT PRO indicators.
- `labels.py`: forward-return labels for supervised research.
- `models.py`: training and `joblib` export boundary.
- `signals.py`: converts model probabilities into entries and exits.
- `portfolios.py`: owns `vbt.Portfolio.from_signals` assumptions.
- `validation.py`: evaluates train/test validation flows and keeps split mechanics out of orchestration.
- `reports.py`: turns IS/OOS portfolio stats into a blunt survival verdict.
- `experiments.py`: config-driven orchestration.
- `cli.py`: one-command runner.

## Run

```bash
python -m research.aegis_research.cli run research/configs/experiments/synthetic_ml_baseline.yaml
```

The default config uses deterministic synthetic OHLCV data, so it is safe for CI and does not require exchange credentials.

## VectorBT PRO Notes

- Use `YFData`, `BinanceData`, or `CCXTData` for real fetches once an experiment needs external data.
- Keep high-cardinality parameter sweeps inside VectorBT indicator/portfolio objects instead of Python loops where possible.
- Use `Portfolio.from_signals` for the first loop; move to `from_order_func` only when signal arrays cannot express the execution model.
- Save only public, non-sensitive run artifacts in git. The `runs/` directory remains ignored except for `.gitkeep`.

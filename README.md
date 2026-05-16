<p align="center">
  <img src="assets/logo.png" alt="Aegis RD" width="260">
</p>

# Aegis RD

Aegis RD is a VectorBT PRO-first research scaffold for trading experiments.

It exists to make market ideas cheap to test, cheap to reject, and easy to explain. The focus is out-of-sample survival, walk-forward evidence, cost-aware portfolio simulation, and clear reports that say why an idea failed or survived.

The goal is to make the core quantitative loop fast, explicit, and easy to reject:

```text
VectorBT PRO data
-> indicators
-> labels
-> validation split
-> model or signal rule
-> Portfolio.from_signals
-> survival report
```

VectorBT PRO is the engine for data access, indicator computation, signal handling, portfolio simulation, statistics, and future walk-forward validation. This repo adds a thin project structure around it so experiments can be run from config and produce repeatable artifacts.

## VectorBT PRO Resources

- [VectorBT PRO](https://vectorbt.pro/pvt_16ebf9ef/)
- [PRO feature overview](https://vectorbt.pro/pvt_16ebf9ef/features/overview/)
- [Open-source VectorBT features](https://vectorbt.dev/getting-started/features/)
- [Tutorials](https://vectorbt.pro/pvt_16ebf9ef/tutorials/overview/)
- [Cookbook](https://vectorbt.pro/pvt_16ebf9ef/cookbook/overview/)
- [API documentation](https://vectorbt.pro/pvt_16ebf9ef/api/)
- [Documentation overview](https://vectorbt.pro/pvt_16ebf9ef/documentation/overview/)

## Current Scaffold

```text
research/
  aegis_research/
    config.py        # typed experiment config
    data.py          # synthetic, CSV, YFData, BinanceData, CCXTData loaders
    indicators.py    # indicator matrix builders using VectorBT PRO + Pandas
    labels.py        # forward-return labels
    splits.py        # chronological train/test split policy
    models.py        # sklearn model training and joblib export
    signals.py       # probabilities -> entries/exits
    portfolios.py    # vbt.Portfolio.from_signals wrapper
    validation.py    # train/test evaluation boundary
    reports.py       # survival verdicts and metrics
    experiments.py   # orchestration and artifact writing
    cli.py           # command runner
  configs/
    experiments/
      synthetic_ml_baseline.yaml
runs/
docs/
```

## Run The Baseline

```bash
python -m research.aegis_research.cli run research/configs/experiments/synthetic_ml_baseline.yaml
```

The baseline uses deterministic synthetic OHLCV data, so it does not require exchange credentials or network access. It trains a simple logistic regression model on indicator-derived inputs, converts model probabilities into entries/exits, runs `vbt.Portfolio.from_signals`, and writes a report under `runs/`.

Example output:

```text
Run: runs/20260516T012248Z_synthetic_ml_baseline
Status: rejected
Reason:
- OOS Sharpe below threshold: -1.100812081585402 < 0.5
```

## VectorBT PRO Concepts Used

- `Data`: fetch or load market data through VectorBT PRO data classes where practical.
- `Indicators`: compute reusable numeric arrays such as returns, moving-average distance, volatility, and RSI.
- `Labels`: create forward-looking targets for supervised experiments.
- `Signals`: convert model outputs or indicator conditions into entries and exits.
- `Portfolio.from_signals`: simulate orders, positions, fees, slippage, returns, drawdowns, and trade stats.
- `Stats`: reduce portfolio results into train/test metrics.

## Public Boundary

This repository may contain generic research workflow code, deterministic baselines, public methodology docs, report schemas, and scaffold examples.

This repository must not contain:

- Real profitable strategy parameters.
- Sensitive run outputs for live candidates.
- Exchange credentials, account identifiers, or execution configuration.
- Proprietary data snapshots.
- Live handoff bundles.
- Anything that reveals deployed edge.

## Artifact Policy

Experiment outputs belong under `runs/`, which is ignored by git except for `runs/.gitkeep`.

Typical run artifacts:

```text
runs/<timestamp>_<experiment>/
  config.yaml
  survival_report.json
  probabilities.csv
  signals.csv
  artifacts/
    model.joblib
```

## Next Architecture Moves

- Replace the simple chronological split with `vbt.Splitter`-backed walk-forward validation.
- Add VectorBT PRO label-generator wrappers such as `FIXLB`, `TRENDLB`, and `PIVOTLB` where useful.
- Add parameter-grid experiments using VectorBT PRO parameterization instead of Python loops.
- Add multi-symbol portfolio handling with grouping and cash-sharing assumptions.
- Add cost sensitivity, regime slicing, bootstrap diagnostics, and handoff bundles only after an idea survives the basic loop.

## Principle

Keep the project thin around VectorBT PRO. Use VectorBT PRO primitives directly where they fit, and add local code only where the project needs repeatable configuration, validation policy, artifact writing, or public-safe reporting.

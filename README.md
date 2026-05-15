# Aegis RD

Aegis RD is a public research and development lab for VectorBT Pro-first trading research.

It exists to make market ideas cheap to test, cheap to reject, and easy to explain. The focus is out-of-sample survival, walk-forward evidence, cost-aware portfolio simulation, and clear reports that say why an idea failed or survived.

[Vectorbt Pro](https://vectorbt.pro/pvt_16ebf9ef/) Sites:

**features**:
[Pro features](https//vectorbt.pro/pvt_16ebf9ef/features/overview/)
[Basic features](https://vectorbt.dev/getting-started/features/)

**examples**:
[Mastering tutorials](https://vectorbt.pro/pvt_16ebf9ef/tutorials/overview/)
[Practical examples](https://vectorbt.pro/pvt_16ebf9ef/cookbook/overview/)

**documentation**:
[API documentation](https://vectorbt.pro/pvt_16ebf9ef/api/)
[documentation](https://vectorbt.pro/pvt_16ebf9ef/documentation/overview/)

## Product Thesis

Research should start from the fastest honest loop:

```text
VectorBT Pro data fetch
-> Python research factors and signals
-> out-of-sample and walk-forward testing
-> portfolio simulation with realistic costs
-> survival report
-> research handoff bundle for survivors
```

VectorBT Pro is the research engine. Python is the lab surface. The output is evidence, not faith in a metric.

## Public Boundary

This repo may contain:

- VectorBT Pro-first research workflow code.
- Generic data-fetch and experiment scaffolding.
- Baseline examples such as SMA or RSI.
- Survival report formats and examples.
- Research handoff bundle schemas and validators.
- Methodology docs for OOS, walk-forward, cost sensitivity, and rejection criteria.

This repo must not contain:

- Real profitable strategy parameters.
- Sensitive run outputs for live candidates.
- Exchange credentials, account identifiers, or execution configuration.
- Proprietary data snapshots.
- Handoff bundles for live strategies.
- Anything that reveals deployed edge.

## Non-Negotiable Goal

One command should answer:

```text
Did this idea survive out-of-sample and portfolio testing?
```

The default output should be blunt. Most ideas should be cheap to reject.

```text
Status: rejected

Reason:
- OOS Sharpe collapsed from 1.4 in-sample to -0.2 out-of-sample
- Edge was concentrated in 1 of 8 walk-forward slices
- Fees erased gross returns
- Not worth productionizing
```

## Why This Exists

The previous Aegis direction made research ideas too production-shaped too early. Feature catalogs, diagnostic workbenches, dataframe handoffs, training paths, and promotion contracts all have value later, but they add friction before the project knows whether a market idea has edge.

This rebuild removes that friction. A research idea should begin as a disposable factor or signal, not as a production feature.

## Vocabulary

- `factor`: a numeric research series derived from market data.
- `signal`: entries, exits, weights, or target sizes derived from one or more factors.
- `experiment`: data, factor, signal, split policy, portfolio assumptions, and parameters run together.
- `survival_report`: the evidence that explains whether the experiment survived or failed.
- `handoff_bundle`: the minimal contract and artifacts for a surviving idea.

Avoid calling research ideas `features` until they are strong enough to promote.

## Initial Scope

The first version should be intentionally small:

- Fetch or load market data directly through VectorBT Pro where practical.
- Define disposable Python factors and signals.
- Run out-of-sample and walk-forward diagnostics.
- Run VectorBT Pro portfolio simulations with fees, slippage, sizing, and timing assumptions.
- Emit survival reports that identify OOS collapse, regime fragility, cost sensitivity, and concentrated edge.
- Emit handoff bundles only for ideas that survive.

## Out Of Scope For The First Loop

- Rebuilding the old Aegis application architecture.
- Reviving the Python archive wholesale.
- Making a diagnostic workbench the center of research.
- Building a production feature catalog before ideas survive.
- Building a custom data lake before the research loop works.
- Treating a clean diagnostic as promotion-ready without OOS and portfolio evidence.

## Handoff Bundle Boundary

Public code defines the bundle schema. Sensitive real-world bundles should not be committed here.

```text
handoff_bundle/
  manifest.yaml
  survival_report.json
  metrics.parquet
  trades.parquet
  equity_curve.parquet
  plots/
  artifacts/
```

The manifest should eventually capture:

- Strategy or signal ID.
- Data source and snapshot identity.
- Symbols, timeframe, and date range.
- Factor and signal definitions.
- Selected parameters.
- Split policy.
- Fees, slippage, sizing, and timing assumptions.
- OOS and portfolio evidence.

## Intended Repo Shape

```text
research/
  aegis_research/
    data.py
    factors.py
    signals.py
    splits.py
    portfolios.py
    diagnostics.py
    reports.py
    cli.py
  configs/
    experiments/
      sma_baseline.yaml
runs/
docs/
```

This shape is provisional. Keep it simple until the first survival report is useful.

## First Milestone

Create the smallest working experiment runner:

```bash
python -m research.aegis_research.cli run research/configs/experiments/sma_baseline.yaml
```

It should:

- Fetch or load data.
- Build one baseline signal.
- Run walk-forward/OOS testing.
- Run a portfolio simulation with costs.
- Save a survival report under `runs/`.
- Say whether the idea survived, failed, or needs more evidence.

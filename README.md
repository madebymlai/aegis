# Aegis RD

Aegis RD is the public research and development lab for Aegis.

It is a VectorBT Pro-first workspace for testing factors, signals, labels, models, and trading ideas before anything is allowed near live runtime code. The private `aegis-trader` repo stays focused on execution, risk, exchange integration, and promoted artifacts.

The old project stalled because the hardest problem was not exchange execution, Rust safety, or application architecture. The blocker was research: testing ideas quickly, seeing whether they survive out-of-sample evidence, and understanding why they fail before spending time on runtime infrastructure.

This repo starts from zero around that problem.

## Product Thesis

Research comes first. Runtime comes later.

```text
VectorBT Pro data fetch
-> Python research factors and signals
-> out-of-sample and walk-forward testing
-> portfolio simulation with realistic costs
-> survival report
-> promotion bundle for survivors
-> private aegis-trader runtime parity and execution
```

VectorBT Pro is the research engine. `aegis-trader` is the robot, not the lab.

## Repository Split

- `aegis-rd`: public research methodology, experiment runner, baseline examples, survival reports, and promotion-bundle schema.
- `aegis-trader`: private runtime, execution adapters, risk controls, live configuration, real promoted bundles, and any strategy edge that should not be public.

Public lab. Private robot.

## Public Boundary

This repo may contain:

- VectorBT Pro-first research workflow code.
- Generic data-fetch and experiment scaffolding.
- Baseline examples such as SMA or RSI.
- Survival report formats and examples.
- Promotion-bundle schemas and validators.
- Methodology docs for OOS, walk-forward, cost sensitivity, and rejection criteria.

This repo must not contain:

- Real profitable strategy parameters.
- Private run outputs for live candidates.
- Exchange credentials, account identifiers, or execution configuration.
- Proprietary data snapshots.
- Promotion bundles for live strategies.
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
- Not worth porting to Rust
```

## Why This Exists

The previous Aegis direction made research ideas too production-shaped too early. Feature catalogs, Feature Forge, Polars handoffs, Rust training paths, and promotion contracts all have value later, but they add friction before the project knows whether a market idea has edge.

This rebuild removes that friction. A research idea should begin as a disposable factor or signal, not as a production feature.

## Vocabulary

- `factor`: a numeric research series derived from market data.
- `signal`: entries, exits, weights, or target sizes derived from one or more factors.
- `experiment`: data, factor, signal, split policy, portfolio assumptions, and parameters run together.
- `survival_report`: the evidence that explains whether the experiment survived or failed.
- `promotion_bundle`: the minimal contract and artifacts for something worth reproducing in `aegis-trader`.

Avoid calling research ideas `features` until they are strong enough to promote.

## Initial Scope

The first version should be intentionally small:

- Fetch or load market data directly through VectorBT Pro where practical.
- Define disposable Python factors and signals.
- Run out-of-sample and walk-forward diagnostics.
- Run VectorBT Pro portfolio simulations with fees, slippage, sizing, and timing assumptions.
- Emit survival reports that identify OOS collapse, regime fragility, cost sensitivity, and concentrated edge.
- Emit promotion bundles only for ideas that survive.

## Out Of Scope For The First Loop

- Rebuilding the old Aegis application architecture.
- Reviving the Python archive wholesale.
- Making Feature Forge the center of research.
- Building a Rust feature catalog before ideas survive.
- Making Rust the primary research runtime.
- Building a custom data lake before the research loop works.
- Treating a clean diagnostic as promotion-ready without OOS and portfolio evidence.

## Promotion Bundle Boundary

Public code defines the bundle schema. Private research decides whether a real bundle should exist.

```text
promotion_bundle/
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
- Fees, slippage, sizing, and execution timing.
- OOS and portfolio evidence.
- Runtime parity requirements.

Real promotion bundles belong in private storage or the private `aegis-trader` repo, not in this public repo.

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

## Runtime Posture

Rust remains valuable, but only after research has produced a survivor.

Runtime work should begin from a promotion bundle and answer:

```text
Can the runtime reproduce and safely execute the behavior VectorBT Pro tested?
```

`aegis-trader` responsibilities later:

- Recompute or replay promoted signals against the same data.
- Compare runtime decisions/trades with VectorBT Pro expectations.
- Enforce risk, sizing, exchange integration, and live execution safety.
- Fail closed when runtime behavior diverges from the promoted manifest.

## Relationship To `aegis-trader`

`aegis-trader` is private because runtime execution, live configuration, promoted artifacts, and real edge are sensitive.

`aegis-rd` is public because the research methodology, scaffolding, and schemas are reusable without exposing live strategy edge.

The intended connection is direct but one-way:

```text
aegis-rd proves an idea and emits a private promotion bundle
-> aegis-trader imports/verifies the bundle
-> aegis-trader executes only if runtime parity and safety checks pass
```

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

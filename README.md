# Aegis Trading

Aegis Trading is a fresh VectorBT Pro-first rebuild of the Aegis research loop.

The old project stalled because the hardest problem was not exchange execution, Rust safety, or application architecture. The blocker was feature research: testing ideas quickly, seeing whether they survive out-of-sample evidence, and understanding why they fail before spending time on runtime infrastructure.

This repo starts from zero around that problem.

## Product Thesis

Research comes first. Runtime comes later.

```text
VectorBT Pro data fetch
-> Python research factors and signals
-> out-of-sample and walk-forward testing
-> portfolio simulation with realistic costs
-> survival report
-> promotion manifest
-> Rust runtime parity and execution only for survivors
```

VectorBT Pro is the research engine. Rust is the robot, not the lab.

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
- `promotion_manifest`: the minimal contract for something worth reproducing in runtime code.

Avoid calling research ideas `features` until they are strong enough to promote.

## Initial Scope

The first version should be intentionally small:

- Fetch or load market data directly through VectorBT Pro where practical.
- Define disposable Python factors and signals.
- Run out-of-sample and walk-forward diagnostics.
- Run VectorBT Pro portfolio simulations with fees, slippage, sizing, and timing assumptions.
- Emit survival reports that identify OOS collapse, regime fragility, cost sensitivity, and concentrated edge.
- Emit promotion manifests only for ideas that survive.

## Out Of Scope For The First Loop

- Rebuilding the old Aegis application architecture.
- Reviving the Python archive wholesale.
- Making Feature Forge the center of research.
- Building a Rust feature catalog before ideas survive.
- Making Rust the primary research runtime.
- Building a custom data lake before the research loop works.
- Treating a clean diagnostic as promotion-ready without OOS and portfolio evidence.

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

Runtime work should begin from a promotion manifest and answer:

```text
Can the runtime reproduce and safely execute the behavior VectorBT Pro tested?
```

Rust responsibilities later:

- Recompute or replay promoted signals against the same data.
- Compare runtime decisions/trades with VectorBT Pro expectations.
- Enforce risk, sizing, exchange integration, and live execution safety.
- Fail closed when runtime behavior diverges from the promoted manifest.

## Relationship To `aegis-trader`

`aegis-trader` is the previous architecture-heavy repo. It remains useful as reference material for exchange integration, runtime safety, historical decisions, and lessons learned.

This repo is the pivot: a research-first rebuild designed around VectorBT Pro from day one.

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

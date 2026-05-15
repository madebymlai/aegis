# Build the VectorBT Pro-first Aegis RD loop from zero

## Goal

Build the first Aegis RD research loop around VectorBT Pro from day one.

The purpose is not to port the old Aegis architecture. The purpose is to solve the problem that paused the previous project: feature and signal research did not reliably tell whether an idea would survive out-of-sample testing and realistic portfolio simulation.

Aegis RD is public. `aegis-trader` remains private. Public RD owns reusable methodology, scaffolding, reports, and schemas. Private Trader owns runtime execution, real promoted bundles, live configuration, and any strategy edge that should not be public.

Target flow:

```text
VectorBT Pro data fetch or load
-> Python factors and signals
-> out-of-sample and walk-forward testing
-> VectorBT Pro portfolio simulation with costs
-> survival report
-> promotion bundle for survivors
-> private aegis-trader runtime parity and execution later
```

## Core Decisions

- Start from a clean research-first repo instead of extending the old Aegis runtime architecture.
- Use licensed `vectorbtpro` as the primary research package.
- Let VectorBT Pro own data fetch/load for the first loop where practical.
- Keep Python as the lab for disposable factors, signals, diagnostics, and reports.
- Do not center the first loop on Feature Forge, Rust feature catalogs, Rust training, Polars boundaries, or production promotion contracts.
- Treat private `aegis-trader` as the later runtime parity and execution target for promoted survivors only.
- Avoid calling research ideas `features` until they survive enough evidence to become promotion candidates.
- Keep real profitable parameters, private run outputs, proprietary data, live promotion bundles, and execution configuration out of public Aegis RD.

## Research Vocabulary

- `factor`: a numeric research series derived from market data.
- `signal`: entries, exits, weights, or target sizes derived from one or more factors.
- `experiment`: data source, factor, signal, split policy, portfolio assumptions, and parameters run together.
- `survival_report`: evidence explaining whether the experiment survived, failed, or needs more testing.
- `promotion_bundle`: a language-neutral contract plus artifacts for ideas worth reproducing in private runtime code.

## Public And Private Boundary

Public Aegis RD can contain:

- Generic VectorBT Pro-first experiment runner code.
- Baseline examples such as SMA crossover or RSI threshold.
- Survival report schemas and example reports.
- Promotion-bundle schemas and validators.
- Methodology docs for OOS, walk-forward, cost sensitivity, and rejection criteria.

Public Aegis RD must not contain:

- Real profitable strategy parameters.
- Private run outputs for live candidates.
- Exchange credentials, account identifiers, or execution configuration.
- Proprietary data snapshots.
- Promotion bundles for live strategies.
- Anything that reveals deployed edge.

## First Implementation Direction

Create a minimal config-driven research runner.

Candidate command:

```bash
python -m research.aegis_research.cli run research/configs/experiments/sma_baseline.yaml
```

Candidate repo shape:

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
```

Keep this shape flexible. The first useful survival report matters more than perfect architecture.

## Survival Report Requirements

The report must make OOS collapse obvious.

It should include:

- Final status: `survived`, `rejected`, or `needs_more_evidence`.
- In-sample versus out-of-sample comparison.
- Walk-forward split metrics.
- Portfolio metrics with fees and slippage.
- Cost sensitivity.
- Turnover and trade count.
- Edge concentration across splits, symbols, or regimes.
- The dominant reason the idea failed or survived.
- Recommended next test, if any.

Example rejected output:

```text
Status: rejected

Reason:
- OOS Sharpe collapsed from 1.4 in-sample to -0.2 out-of-sample
- Edge was concentrated in 1 of 8 walk-forward slices
- Fees erased gross returns
- Not worth porting to Rust
```

## Baseline Experiment Requirements

The first experiment should be boring and deterministic.

- Use a simple baseline such as SMA crossover or RSI threshold.
- Fetch or load data through VectorBT Pro if practical.
- Configure symbol, timeframe, date range, fees, slippage, sizing, and execution timing.
- Split data into train/test or rolling walk-forward windows.
- Select parameters without using the final holdout.
- Run portfolio simulation through VectorBT Pro.
- Save config, metrics, trades/orders if available, equity curve, and survival report under `runs/`.

## Out Of Scope

- Reviving the entire Python archive.
- Porting the old Rust architecture.
- Rebuilding Feature Forge before the research loop works.
- Adding a Rust feature catalog before a signal survives.
- Requiring Polars as an internal boundary for the first loop.
- Building a custom data lake.
- Implementing live trading.
- Treating any metric-only diagnostic as promotion-ready.

## Promotion Bundle And Runtime Handoff Later

Only after an idea survives should the project emit a promotion bundle.

The bundle should eventually include:

- `manifest.yaml` with strategy or signal ID, selected parameters, runtime parity requirements, and compatibility metadata.
- `survival_report.json` with rejection/survival evidence.
- Metrics, trades, orders, returns, equity curve, and plots where safe to store.
- Data source identity, symbols, timeframe, date range, and split policy.
- Fees, slippage, sizing, and execution timing assumptions.
- Factor and signal definitions needed for runtime parity.

Real promotion bundles stay private. `aegis-trader` should start from a bundle and answer whether live/runtime behavior can reproduce the tested VectorBT Pro behavior safely.

## Acceptance Criteria

- [ ] The repo has a clean public Aegis RD / private Aegis Trader README boundary.
- [ ] Research code imports `vectorbtpro`, not open-source `vectorbt`.
- [ ] One command runs a deterministic baseline experiment from config.
- [ ] The baseline fetches or loads data without depending on the old Aegis runtime architecture.
- [ ] The baseline runs OOS or walk-forward evaluation.
- [ ] The baseline runs a VectorBT Pro portfolio simulation with fees and slippage.
- [ ] The run emits a survival report under `runs/`.
- [ ] The report clearly identifies OOS collapse when it happens.
- [ ] The report distinguishes `survived`, `rejected`, and `needs_more_evidence`.
- [ ] The public repo keeps live/private edge artifacts out of source control.
- [ ] Private `aegis-trader` runtime work remains deferred until a promotion bundle exists.

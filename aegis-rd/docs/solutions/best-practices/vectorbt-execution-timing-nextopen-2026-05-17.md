---
title: Model Execution Timing Explicitly in VectorBT Backtests
date: 2026-05-17
category: best-practices
module: vectorbtpro.portfolio
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - building daily stock backtests from close-based signals or weights
  - deciding whether a signal should fill on the current close or next open
  - reviewing a backtest for hidden execution-timing assumptions
tags:
  - vectorbtpro
  - backtesting
  - execution-timing
  - nextopen
  - lookahead-bias
---

# Model Execution Timing Explicitly in VectorBT Backtests

## Context

VectorBT executes orders on the same bar by default, using the current close price. That default is valid when the modeled strategy can observe the signal and trade quickly enough at or near the close, but it is an assumption that should be made explicit.

In Discord support, the maintainer clarified that VBT does not automatically delay signal execution to the next bar. A daily signal generated from today's close can fill at today's close unless the strategy shifts the signal or uses a next-open execution price.

## Guidance

Treat execution timing as part of the strategy contract. Before trusting a backtest, decide which timestamp the signal observes and which timestamp the trade can realistically execute.

VectorBT's default behavior is same-bar execution at the current close:

```python
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
)
```

For daily stock strategies where signals are computed from the closing price and the trade should happen after that close is known, prefer one of these explicit patterns.

Use next-open execution:

```python
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    price="nextopen",
)
```

Or shift close-derived signals by one bar:

```python
entries = (close > vbt.MA.run(close, 8, ewm=True).ma).shift(1).fillna(False)

pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits.shift(1).fillna(False),
)
```

For target-percent allocation backtests, apply the same rule to weights. If weights are computed from today's close but should trade after today's close is known, shift them before passing them as orders:

```python
weights = compute_weights(close)
tradable_weights = weights.shift(1).fillna(0)

pf = vbt.Portfolio.from_orders(
    close=close,
    size=tradable_weights,
    size_type="targetpercent",
    group_by=True,
    cash_sharing=True,
    call_seq="auto",
)
```

Same-close execution can still be reasonable when the model intentionally assumes closing auction participation, near-close data availability, intraday signal updates, or slippage large enough to cover reaction delay. The important part is that the assumption is explicit.

## Why This Matters

Execution timing changes both performance and validity. If a daily stock backtest computes a signal using the final close and then fills at that same close, it may overstate live tradability unless the strategy can actually act at that time.

For equities, next-open execution is often more conservative because overnight gaps are real and the close is usually only fully known after the bar completes. For crypto or higher-frequency systems, same-bar execution may be more defensible if the trading system reacts to live data fast enough.

## When to Apply

- Apply this whenever signals or weights depend on the same bar's close.
- Apply this when reviewing whether a backtest has lookahead-like assumptions even if it does not technically peek into future rows.
- Apply this before comparing a custom strategy against buy-and-hold or ETF benchmarks.
- Apply this when porting notebook logic into reusable experiments so the fill timing is not hidden in defaults.

## Examples

The core review question is: "Could the strategy have placed this order at the price used by the simulator?"

If the strategy observes today's close and fills at today's close, document why that is realistic:

```python
# Same-close execution is intentional: model assumes closing auction participation.
pf = vbt.Portfolio.from_signals(close, entries, exits, slippage=0.001)
```

If the strategy observes today's close but can only trade after the close is known, use next-open or shifted execution:

```python
# Close-derived signal, next-open execution.
pf = vbt.Portfolio.from_signals(close, entries, exits, price="nextopen")
```

## Related

- Discord support thread on current-close execution and `price="nextopen"`: https://discord.com/channels/918629562441695344/918630948248125512/991066395724894249
- Discord support note recommending one-bar shifts for close-derived daily portfolio weights: https://discord.com/channels/918629562441695344/918630948248125512/1293124495019606108
- [Avoid Universe Bias in Historical Index Backtests](./nasdaq-100-backtest-universe-bias-2026-05-17.md)

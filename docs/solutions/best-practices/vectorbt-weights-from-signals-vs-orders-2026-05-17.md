---
title: Choose the Right VectorBT Portfolio Constructor for Weights and Signals
date: 2026-05-17
category: best-practices
module: vectorbtpro.portfolio
problem_type: best_practice
component: tooling
severity: low
applies_when:
  - assigning portfolio weights in from_signals
  - choosing between from_signals and from_orders
  - combining signal logic with target position sizing
tags:
  - vectorbtpro
  - from-signals
  - from-orders
  - weights
  - targetpercent
  - valuepercent
---

# Choose the Right VectorBT Portfolio Constructor for Weights and Signals

## Context

A Discord support question asked how to assign weights when using `Portfolio.from_signals`. The user had a weight matrix similar to a `from_orders` target-percent setup and wanted to know whether `from_signals` should be used instead.

The maintainer clarified two cases: if there are only weights and no separate signals, use `from_signals` with `order_mode=True`, `size=...`, and `size_type="targetpercent"`; if there are actual entry/exit signals, use the `valuepercent` sizer.

## Guidance

Choose the constructor based on what your data represents.

If the dataframe already contains desired portfolio weights, `from_orders` is usually the direct representation:

```python
pf = vbt.Portfolio.from_orders(
    close=close,
    size=weights,
    size_type="targetpercent",
    group_by=True,
    cash_sharing=True,
    call_seq="auto",
)
```

If you want to use `from_signals` but only have weights, enable order mode so the weights generate orders:

```python
pf = vbt.Portfolio.from_signals(
    close=close,
    size=weights,
    size_type="targetpercent",
    order_mode=True,
    group_by=True,
    cash_sharing=True,
)
```

If you have real entry/exit signals and want to size trades as a fraction of portfolio value, use a value-percent sizing mode instead of treating the weights as independent target allocations:

```python
pf = vbt.Portfolio.from_signals(
    close=close,
    entries=entries,
    exits=exits,
    size=sizes,
    size_type="valuepercent",
    group_by=True,
    cash_sharing=True,
)
```

## Why This Matters

Weights, orders, and signals are different contracts. A target weight says what exposure the portfolio should have after rebalancing. A signal says when an entry or exit event should happen. Mixing those concepts can lead to double interpretation: a weight matrix may be treated like signal sizing, or signal sizing may be treated like target allocation.

Using the constructor that matches the data shape keeps the backtest easier to reason about and easier to debug.

## When to Apply

- Apply this when a notebook has `filled_allocations`, `weights`, or target exposures but no independent entry/exit signal arrays.
- Apply this when converting an optimizer output into a portfolio simulation.
- Apply this when a strategy has both signal timing and desired trade size.

## Examples

Use `from_orders` for rebalance weights:

```python
pf = vbt.Portfolio.from_orders(close, size=filled_allocations, size_type="targetpercent")
```

Use `from_signals` for signal events:

```python
pf = vbt.Portfolio.from_signals(close, entries=entries, exits=exits, size=0.25, size_type="valuepercent")
```

## Related

- Discord support thread on weights with `from_signals`: https://discord.com/channels/918629562441695344/918630948248125512/1409560434750656686
- [Diagnose NoCash Rejections in Target-Percent Rebalancing](./vectorbt-targetpercent-nocash-rejections-2026-05-17.md)

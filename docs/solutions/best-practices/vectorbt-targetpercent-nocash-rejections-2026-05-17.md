---
title: Diagnose NoCash Rejections in Target-Percent Rebalancing
date: 2026-05-17
category: best-practices
module: vectorbtpro.portfolio
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - using targetpercent orders with cash_sharing enabled
  - rebalancing long-short portfolios from weight matrices
  - seeing fewer executed positions than requested weights
tags:
  - vectorbtpro
  - targetpercent
  - nocash
  - cash-sharing
  - rebalancing
  - long-short
---

# Diagnose NoCash Rejections in Target-Percent Rebalancing

## Context

A recurring VectorBT confusion is that a target-percent weight matrix can request balanced long and short exposure, but the realized portfolio may hold fewer positions than requested. In the Discord thread, the user's logs showed rejected orders with `NoCash` even though `call_seq="auto"` was enabled.

The maintainer clarified that `call_seq="auto"` considers sell requests, but it cannot guarantee that a sell will free cash. A short position that is losing may require cash to close, so the sell itself can fail when the portfolio is fully allocated.

## Guidance

When a target-percent rebalance does not match the intended weights, inspect the order logs before assuming the weights are wrong. Rejections often come from cash constraints, not from ranking or allocation logic.

Common setup:

```python
pf = vbt.Portfolio.from_orders(
    close=close,
    size=weights[close.columns],
    size_type="targetpercent",
    price=close,
    fees=fees,
    init_cash=init_cash,
    cash_sharing=True,
    group_by=True,
    freq="1D",
    call_seq="auto",
)
```

If the result holds fewer long or short positions than expected, check the logs for rejection status and reason. A `NoCash` rejection means the simulator could not execute the order under the portfolio cash model.

Practical guardrails:

```python
weights = weights.reindex(columns=close.columns).fillna(0)

# Leave cash buffer for fees, slippage, and losing short closures.
gross_exposure = weights.abs().sum(axis=1)
weights = weights.div(gross_exposure.where(gross_exposure > 0), axis=0).fillna(0) * 0.95
```

For futures or margin-heavy strategies, do not assume VectorBT's stock-style cash model matches the broker model. The maintainer noted that futures support was not currently modeled as full futures margin behavior in that thread, and negative cash balances were not generally available as a workaround.

## Why This Matters

Unnoticed `NoCash` rejections can turn a market-neutral or balanced strategy into an unintended net-exposure strategy. The requested weights may sum to the desired long and short totals, while the executed trades do not.

This matters most for long-short, leveraged, and margin-like strategies because closing losing shorts can require available cash. `call_seq="auto"` can help sequence orders, but it cannot create cash that the model says is unavailable.

## When to Apply

- Apply this when `pf.plot_allocations()` does not match the requested weight matrix.
- Apply this when target weights request both positive and negative exposure.
- Apply this when order logs show `NoCash` or unexplained rejected orders.
- Apply this before treating missing positions as a ranking bug.

## Examples

Bad assumption:

```python
# Assumption: call_seq="auto" guarantees all sells execute before buys.
pf = vbt.Portfolio.from_orders(..., call_seq="auto")
```

Better review posture:

```python
# call_seq="auto" helps sequencing, but rejected orders still need log review.
orders = pf.orders.records_readable
logs = pf.logs.records_readable
```

If the logs show `NoCash`, reduce gross exposure, add cash buffer, adjust fees/slippage, or choose a simulation model that represents the intended instrument and margin behavior.

## Related

- Discord support thread on target-percent weights, `NoCash`, and `call_seq="auto"`: https://discord.com/channels/918629562441695344/918630948248125512/1363144608481153214
- [Model Execution Timing Explicitly in VectorBT Backtests](./vectorbt-execution-timing-nextopen-2026-05-17.md)

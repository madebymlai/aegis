---
title: Close Optimizer Allocations at the Final Bar Manually
date: 2026-05-17
category: best-practices
module: vectorbtpro.portfolio
problem_type: best_practice
component: tooling
severity: low
applies_when:
  - using Portfolio.from_optimizer with allocation outputs
  - needing all positions closed at the end of a simulation
  - comparing optimizer runs where open final positions would distort stats
tags:
  - vectorbtpro
  - optimizer
  - close-at-end
  - allocations
  - from-orders
---

# Close Optimizer Allocations at the Final Bar Manually

## Context

`close_at_end` is not a universal portfolio option for every construction path. In Discord support, the maintainer confirmed that `close_at_end` applies to `Portfolio.from_holding` but not to `Portfolio.from_optimizer` in the discussed workflow.

When optimizer allocations should be fully closed on the last simulated date, the maintainer recommended extracting the allocation matrix, setting the last row to zero, and passing the result through `Portfolio.from_orders`.

## Guidance

Make the terminal liquidation explicit in the allocation matrix.

```python
allocations = optimizer.fill_allocations()
allocations.iloc[-1] = 0

pf = vbt.Portfolio.from_orders(
    close=close,
    size=allocations,
    size_type="targetpercent",
    group_by=True,
    cash_sharing=True,
    call_seq="auto",
)
```

This keeps the optimizer responsible for producing target allocations and makes the final closeout a visible portfolio-construction step.

## Why This Matters

Leaving final positions open can distort comparisons when a report expects realized results only, when cash at the end is required for downstream accounting, or when multiple optimizer runs are stitched together.

Explicitly zeroing the final allocation row avoids assuming that `from_optimizer` will apply closeout behavior that belongs to another construction method.

## When to Apply

- Apply this when portfolio stats should reflect liquidation by the final timestamp.
- Apply this when the portfolio was built from optimizer allocations rather than a buy-and-hold helper.
- Apply this when comparing runs where some strategies finish invested and others finish in cash.

## Examples

Before:

```python
pf = vbt.Portfolio.from_optimizer(...)
```

After:

```python
allocations = optimizer.fill_allocations()
allocations.iloc[-1] = 0

pf = vbt.Portfolio.from_orders(
    close=close,
    size=allocations,
    size_type="targetpercent",
    group_by=True,
    cash_sharing=True,
    call_seq="auto",
)
```

## Related

- Discord support thread on `close_at_end` and optimizer allocations: https://discord.com/channels/918629562441695344/918630948248125512/1046433842195611749

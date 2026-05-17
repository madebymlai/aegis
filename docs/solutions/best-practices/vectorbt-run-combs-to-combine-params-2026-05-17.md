---
title: Prefer combine_params Over run_combs for Indicator Grids
date: 2026-05-17
category: best-practices
module: vectorbtpro.indicators
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - combining multiple indicator instances with paired or constrained parameters
  - seeing tuple outputs from run_combs
  - migrating older VectorBT examples to current parameter workflows
tags:
  - vectorbtpro
  - run-combs
  - combine-params
  - supertrend
  - optimization
---

# Prefer combine_params Over run_combs for Indicator Grids

## Context

Older examples and tutorials may use `run_combs`, but Discord support guidance now points users toward `vbt.combine_params` for building parameter grids. A common symptom is calling `run_combs`, then trying to access an output like `.direction` and getting `AttributeError: 'tuple' object has no attribute 'direction'`.

The maintainer clarified that `run_combs` returns multiple indicator instances as a tuple and recommended building the parameter grid with `combine_params` instead.

## Guidance

Avoid this pattern for new work:

```python
sst = vbt.SUPERTREND.run_combs(
    high,
    low,
    close,
    period=atr_values,
    multiplier=factor_values,
    param_product=True,
)

# Fails because sst may be a tuple of indicator instances.
sst.direction
```

Build the grid first, then run the indicator with concrete parameter arrays:

```python
params = vbt.combine_params(
    dict(
        sst_period=vbt.Param(atr_l_sst),
        sst_multiplier=vbt.Param(factor_sst),
        lst_period=vbt.Param(atr_l_lst),
        lst_multiplier=vbt.Param(factor_lst),
    ),
    build_grid=True,
    build_index=False,
)

sst = vbt.SUPERTREND.run(
    high,
    low,
    close,
    period=params["sst_period"],
    multiplier=params["sst_multiplier"],
    param_product=False,
)

lst = vbt.SUPERTREND.run(
    high,
    low,
    close,
    period=params["lst_period"],
    multiplier=params["lst_multiplier"],
    param_product=False,
)
```

Now outputs such as `sst.direction` and `lst.direction` are regular indicator outputs that can be combined into entries and exits.

## Why This Matters

`combine_params` separates grid construction from indicator execution. That makes the parameter combinations inspectable, compatible with constrained grids, and less surprising than tuple-returning combination helpers.

## When to Apply

- Apply this when examples using `run_combs` produce tuple outputs.
- Apply this when two indicator instances need coordinated parameter combinations.
- Apply this when a custom indicator needs a modern optimization workflow.

## Examples

Review question: "Am I combining indicator instances, or am I building a parameter grid?" If the answer is parameter grid, start with `vbt.combine_params`.

## Related

- Discord support thread recommending `combine_params` over `run_combs`: https://discord.com/channels/918629562441695344/918630948248125512/1350081282930905138
- [Build Parameter Grids with combine_params Before Simulation](./vectorbt-combine-params-conditions-levels-2026-05-17.md)

---
title: Build Parameter Grids with combine_params Before Simulation
date: 2026-05-17
category: best-practices
module: vectorbtpro.optimization
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - enforcing constraints such as fast window less than slow window
  - passing parameter combinations into IndicatorFactory apply functions
  - deciding when Param levels should link parameters instead of forming products
tags:
  - vectorbtpro
  - combine-params
  - optimization
  - param-levels
  - indicatorfactory
---

# Build Parameter Grids with combine_params Before Simulation

## Context

Parameter optimization gets confusing when constraints, parameter levels, and `IndicatorFactory` are mixed together. In Discord, the maintainer clarified two important rules: `IndicatorFactory` apply functions do not accept `vbt.Param` objects directly, and `level=0` is not a generic setting for every parameter grid.

## Guidance

Use `vbt.combine_params` to build the concrete parameter grid first, especially when enforcing constraints.

```python
windows = np.arange(5, 250, 5)

param_product = vbt.combine_params(
    dict(
        lookback_fast=vbt.Param(
            windows,
            condition="lookback_fast < lookback_slow and lookback_fast < 75",
        ),
        lookback_slow=vbt.Param(windows),
    ),
    build_index=False,
    build_grid=True,
)
```

Then pass the resulting arrays into the indicator or simulation:

```python
indicator = MY_IND.run(
    close,
    lookback_fast=param_product["lookback_fast"],
    lookback_slow=param_product["lookback_slow"],
)
```

Use parameter levels deliberately. Parameters at the same level are linked rather than expanded into a full product. That is useful when two settings must move together, but wrong when you want all combinations.

```python
# Linked parameters: same level.
sl_stop = vbt.Param(sl_values, level=0)
tsl_stop = vbt.Param(sl_values, level=0)

# Independent product with take profit.
tp_stop = vbt.Param(tp_values, level=1)
```

## Why This Matters

Improper parameter construction can produce shape errors, invalid combinations, or far more combinations than intended. Preparing the grid explicitly makes the optimization contract visible and keeps Numba/indicator functions receiving plain parameter values rather than `Param` wrappers.

## When to Apply

- Apply this when conditions depend on multiple parameters.
- Apply this when an `IndicatorFactory` apply function errors after receiving parameter-like objects.
- Apply this when parameters should be linked rather than crossed.

## Examples

Wrong pattern for `IndicatorFactory` apply functions:

```python
# Avoid passing vbt.Param directly into a numba apply function.
MY_IND.run(close, fast=vbt.Param(fast_values), slow=vbt.Param(slow_values))
```

Safer pattern:

```python
params = vbt.combine_params(
    dict(
        fast=vbt.Param(windows, condition="fast < slow"),
        slow=vbt.Param(windows),
    ),
    build_grid=True,
    build_index=False,
)

MY_IND.run(close, fast=params["fast"], slow=params["slow"])
```

## Related

- Discord support thread on `combine_params`, conditions, and `IndicatorFactory`: https://discord.com/channels/918629562441695344/918630948248125512/1293283893952380989
- [Diagnose NoCash Rejections in Target-Percent Rebalancing](./vectorbt-targetpercent-nocash-rejections-2026-05-17.md)

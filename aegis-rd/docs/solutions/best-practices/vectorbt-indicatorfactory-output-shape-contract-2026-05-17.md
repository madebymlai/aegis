---
title: Keep IndicatorFactory Outputs the Same Shape as Inputs
date: 2026-05-17
category: best-practices
module: vectorbtpro.indicators
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - building custom indicators with IndicatorFactory
  - returning transformed series such as Renko bricks from tick data
  - deciding whether to use IndicatorFactory or parameterized pipelines
tags:
  - vectorbtpro
  - indicatorfactory
  - custom-indicators
  - output-shape
  - parameterized
---

# Keep IndicatorFactory Outputs the Same Shape as Inputs

## Context

`IndicatorFactory` is designed for indicators whose outputs align with the input wrapper. A common failure mode appears when an indicator compresses or expands data, such as converting 182,676 ticks into 10 Renko bricks. The custom logic may be correct, but it no longer satisfies the indicator output shape contract.

In Discord support, the maintainer clarified that each indicator output must match the input shape. If the output can have a different shape or arbitrary type, use `@vbt.parameterized` as a micro-pipeline instead.

## Guidance

Use `IndicatorFactory` when each output is indexed like the input:

```python
MY_IND = vbt.IF(
    input_names=["close"],
    param_names=["window"],
    output_names=["value"],
).with_apply_func(apply_func, keep_pd=True)

out = MY_IND.run(close, window=20)
```

Do not use `IndicatorFactory` when the output naturally has a different number of rows:

```python
# Not a good IndicatorFactory fit: Renko bricks may be fewer than source ticks.
renko_bricks = build_renko_from_ticks(ticks, brick_size)
```

Use a parameterized function for arbitrary output shapes or return types:

```python
@vbt.parameterized(merge_func="concat")
def renko_pipeline(ticks, brick_size):
    return build_renko_from_ticks(ticks, brick_size)

results = renko_pipeline(ticks, brick_size=vbt.Param([5, 10, 20]))
```

## Why This Matters

For a standard indicator, VectorBT can attach outputs to the same index, columns, and parameter levels as the inputs. Shape-changing transforms break that mapping. Forcing them into `IndicatorFactory` usually leads to errors such as an output shape like `(10, 1)` not matching an input wrapper shape like `(182676, 1)`.

## When to Apply

- Apply this before wrapping custom NumPy or Numba logic with `IndicatorFactory`.
- Apply this when the output represents events, compressed bars, trades, labels, or custom objects rather than one value per input bar.
- Apply this when optimizing parameters for a transform whose output length changes by parameter value.

## Examples

Good `IndicatorFactory` fit:

```python
# One moving-average value per input close row.
ma = vbt.MA.run(close, window=20).ma
```

Poor `IndicatorFactory` fit:

```python
# Renko output count depends on price movement and brick size.
bricks = build_renko_from_ticks(ticks, brick_size=10)
```

## Related

- Discord support thread on Renko output shape mismatch: https://discord.com/channels/918629562441695344/918630948248125512/1034866543860916275

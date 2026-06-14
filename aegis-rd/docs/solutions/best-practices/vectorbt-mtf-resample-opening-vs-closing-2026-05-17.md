---
title: Choose Resample Opening or Closing by Data Availability
date: 2026-05-17
category: best-practices
module: vectorbtpro.resampling
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - aligning higher-timeframe indicators to a lower-timeframe index
  - building multi-timeframe strategies from OHLCV data
  - reviewing resampling choices for lookahead risk
tags:
  - vectorbtpro
  - multi-timeframe
  - resampling
  - resample-opening
  - resample-closing
  - lookahead-bias
---

# Choose Resample Opening or Closing by Data Availability

## Context

Multi-timeframe strategies need to align values computed on a higher timeframe, such as `4h`, to a lower timeframe, such as `30m`. The key question is not only the source and target frequency, but when each value becomes knowable inside the higher-timeframe bar.

In Discord, the maintainer summarized the rule: the resampling method suffix should reflect the data. Opening data is available at the start of the bar, while most close-derived indicators are only available when the bar closes.

## Guidance

Use `resample_opening` for values that are known at the bar open or that represent previous/opening information. Use `resample_closing` for values that depend on the bar close, high, low, or a completed indicator value.

For a higher-timeframe indicator computed from close prices, align with closing semantics:

```python
resampler_h4_m30 = vbt.Resampler(
    source_index=h4_rsi.index,
    target_index=m30_close.index,
    source_freq="4h",
    target_freq="30t",
)

m30_h4_rsi = h4_rsi.vbt.resample_closing(resampler_h4_m30)
```

For a value based exclusively on the higher-timeframe open, align with opening semantics:

```python
m30_h4_open = h4_open.vbt.resample_opening(resampler_h4_m30)
```

Do not infer the method from the column name alone. Infer it from the information the value uses. An indicator using only open can use opening semantics. An indicator using high, low, close, or any completed candle statistic should use closing semantics.

## Why This Matters

The wrong alignment can create subtle lookahead. A close-derived `4h` RSI should not be available to `30m` bars before the `4h` bar has closed. Conversely, treating open-only values as closing values can delay information unnecessarily and distort signal timing.

## When to Apply

- Apply this whenever a higher-timeframe series is realigned to a lower-timeframe index.
- Apply this after running indicators on the higher timeframe.
- Apply this before combining multi-timeframe signals in `Portfolio.from_signals` or `Portfolio.from_orders`.

## Examples

Opening-only data:

```python
h1_h4_open = h4_open.vbt.resample_opening("1h")
```

Close-derived data:

```python
h1_h4_close = h4_close.vbt.resample_closing("1h")
h1_h4_rsi = h4_rsi.vbt.resample_closing("1h")
```

Review question: "Could this higher-timeframe value have been known at the start of the source bar?" If yes, opening alignment may be correct. If no, use closing alignment.

## Related

- Discord thread on `resample_opening` vs `resample_closing`: https://discord.com/channels/918629562441695344/918629563469295628/1026140316778106911
- [Model Execution Timing Explicitly in VectorBT Backtests](./vectorbt-execution-timing-nextopen-2026-05-17.md)

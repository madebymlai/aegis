---
title: Downsample OHLC Data with Aggregation Not Realignment
date: 2026-05-17
category: logic-errors
module: vectorbtpro.resampling
problem_type: logic_error
component: tooling
symptoms:
  - Downsampled high or low values differ from expected candle high and low values
  - Higher-timeframe candles built from lower-timeframe data have incorrect OHLC ranges
  - Resampling close and open looks correct while high and low look wrong
root_cause: wrong_api
resolution_type: code_fix
severity: medium
tags:
  - vectorbtpro
  - ohlc
  - resampling
  - downsampling
  - aggregation
---

# Downsample OHLC Data with Aggregation Not Realignment

## Problem

When converting lower-timeframe OHLCV data into higher-timeframe candles, `resample_opening` and `resample_closing` are the wrong tools for high and low aggregation. They realign latest available values; they do not compute the high or low across the whole target candle.

## Symptoms

- `Open` and `Close` look plausible after resampling, but `High` and `Low` are wrong.
- A 1h candle high equals the latest source high instead of the maximum high inside the 1h window.
- A 1h candle low equals the latest source low instead of the minimum low inside the 1h window.

## What Didn't Work

- Applying `resample_closing` to `High` and `Low` when creating higher-timeframe candles.
- Treating realignment methods as if they aggregated all lower-timeframe rows inside the destination bar.

## Solution

Use aggregation for downsampling OHLCV. For raw pandas data:

```python
h1_ohlcv = m1_ohlcv.resample("1h").agg(
    {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
)
```

For VectorBT data objects, prefer the data object's native resampling when feature configuration is available:

```python
h1_data = m1_data.resample("1h")
```

Use `resample_opening` and `resample_closing` for upsampling or realigning already-computed values to another index, not for constructing higher-timeframe candles from raw lower-timeframe OHLCV.

## Why This Works

Downsampling creates a new candle from many source candles. That requires an aggregation rule per field: first open, max high, min low, last close, and summed volume. Realignment only selects the latest known source value for each target timestamp, so it cannot produce true candle highs and lows.

## Prevention

- Keep separate helper functions for OHLCV downsampling and indicator realignment.
- Treat `resample_opening` and `resample_closing` as availability/alignment tools, not candle builders.
- Add a small test that validates `High` equals the source-window maximum and `Low` equals the source-window minimum.

## Related Issues

- Discord support thread on high and low values after resampling: https://discord.com/channels/918629562441695344/918630948248125512/955639661655638056
- [Choose Resample Opening or Closing by Data Availability](../best-practices/vectorbt-mtf-resample-opening-vs-closing-2026-05-17.md)

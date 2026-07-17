---
title: Cat-bond carry signal validation
date: 2026-07-12
status: preliminary
---

# Cat-bond carry signal validation

## Question

Does the causal Artemis market richness signal forecast subsequent catastrophe-bond returns?

## Design

- Signal: weekly insurance spread minus expected loss, expressed as its causal trailing
  104-observation percentile.
- Availability: each Artemis observation delayed seven calendar days.
- Return proxy: SHRIX adjusted NAV from Yahoo Finance, 2013-02-01 through 2026-07-10.
- Horizons: 21, 63, 126 and 252 trading days.
- Strategy comparison: monthly 5%-25% richness sizing versus fixed exposure matched to the
  timed strategy's 13.68% average exposure. Cash return and transaction costs are omitted.
- Boundary: SHRIX is a different manager and US open-end fund with broader reinsurance
  permissions. It validates a market mechanism, never CATB's own track record.

## Results

| Horizon | Weekly overlapping Spearman | Top-minus-bottom forward return | Non-overlapping Spearman | Non-overlapping p-value |
|---|---:|---:|---:|---:|
| 1 month | 0.117 | 0.59% | 0.136 | 0.081 |
| 3 months | 0.201 | 1.78% | 0.254 | 0.062 |
| 6 months | 0.129 | 2.73% | 0.229 | 0.250 |
| 12 months | 0.349 | 7.50% | 0.297 | 0.324 |

The overlapping observations show a monotonic positive direction but their naive p-values
are invalid because adjacent forward returns share most of the same days. The non-overlapping
samples retain the positive sign but do not reject zero at 5%.

The monthly timed rule returned 0.72% annualized at 0.80% volatility and -3.29% maximum
drawdown. Fixed matched exposure returned 0.55% annualized at 0.77% volatility and -2.84%
maximum drawdown. Timing added 0.17 percentage points annually before costs while worsening
maximum drawdown by 0.45 percentage points. Its annual-return advantage was +0.39 points in
2013-2017, +0.29 in 2018-2021, and -0.17 in 2022-2026.

## Verdict

The richness signal has weak, directionally consistent forecasting evidence, strongest at
three and twelve months, but the executable timing rule is not robustly validated. Current
evidence does not justify replacing a fixed cat-bond allocation with active timing. Keep the
signal as a report and challenger overlay; treat a fixed allocation as the parsimonious
baseline until an independent total-return proxy and more non-overlapping history confirm it.

## Required follow-up

1. Repeat on the Swiss Re Global Cat Bond Total Return Index if a licensed series is obtained.
2. Add cash return and CATB-like fees, FX and turnover costs.
3. Freeze thresholds before testing another proxy.
4. Compare fixed and timed cat-bond sleeves inside the full Atalanta floor.

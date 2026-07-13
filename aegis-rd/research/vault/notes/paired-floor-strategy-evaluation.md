---
title: Paired Floor Strategy Evaluation
date: 2026-07-13
topic: portfolio-evaluation
distilled-into:
tags:
  - note
  - evaluation
  - floor
  - carry
---

# Paired Floor Strategy Evaluation

> [!abstract] Decision
> Compare locked strategy configs, not hand-built return proxies or sweep winners. Reproduce each config through the production market-data, Component, allocation and portfolio-simulation path; align full common months; compare the pre-declared fixed-weight floor with trend alone; and jointly resample the paired monthly observations in circular blocks. The result is descriptive whenever the same history helped select either lock. It is not a fresh promotion test.

## Question

The evaluator answers one narrow question:

> Does adding one already-selected carry config at a pre-declared weight improve the realized whole-floor return stream relative to the already-selected trend config?

It does not select either config, reproduce the live Aegis Trader covariance allocator, or infer a production risk budget from research weights. Those are different decisions. The current script implements the fixed `60/40` monthly return mix pre-registered by [[the-skew-is-the-product]], with no hindsight leg-volatility normalization.

The command is:

```bash
uv run python scripts/floor_gate.py \
  --trend research/configs/atalanta/trend_floor.yaml \
  --carry research/configs/demeter/credit_bucket.yaml
```

Both paths must resolve to valid Run Configs with top-level Locks. An unlocked sweep is rejected before market data loads. Each locked Candidate is then reproduced through the same source precompute, strategy allocation, declared execution timing, currency conversion, distributions, drift bands and cost-bearing portfolio simulation used by the optimizer.

## Why these measures

DeMiguel, Garlappi and Uppal compare portfolio rules out of sample with Sharpe ratio, certainty-equivalent return and turnover; their larger result is that estimation error and trading costs can erase apparent optimization gains.[^demiguel] Sharpe alone is not sufficient here because a carry sleeve is intentionally non-normal. Goetzmann, Ingersoll, Spiegel and Welch derive a manipulation-proof measure from power utility and continuously compounded excess returns; Aegis uses the corresponding MPPM certainty equivalent as the primary economic reading.[^gisw]

The report therefore keeps a small hierarchy:

1. MPPM certainty-equivalent delta: did the fixed composite improve economic utility?
2. Sharpe delta: did return per unit of realized volatility improve?
3. Maximum drawdown, worst month and skew: what payoff shape was exchanged?
4. Full-sample and trend-worst-decile dependence: did carry diversify where trend was weak?

The script reports rather than gates. A lower drawdown with lower certainty equivalent is a trade-off, not an automatic pass or failure.

## Dependence-aware uncertainty

Ledoit and Wolf show that normal/IID Sharpe-difference tests are invalid for heavy-tailed or serially dependent returns. Their preferred inference jointly resamples paired return vectors in a circular block bootstrap and uses a studentized confidence interval.[^ledoitwolf] The Aegis script preserves the essential paired-block contract but does **not** claim to reproduce the full Ledoit-Wolf studentization and semi-parametric calibration. It reports percentile intervals as descriptive uncertainty.

Block length materially changes dependent-bootstrap inference. Politis and White provide automatic selectors, corrected by Patton, Politis and White.[^pw][^ppw] That selector is statistic- and dependence-specific. Rather than hide a guessed optimum in a small 70-month sample, the script reports the same result at `1`, `3` and `6` month circular blocks. A conclusion is stable only if it survives that sensitivity.

White's Reality Check addresses a different problem: inference after searching many models on the same history.[^white] The floor evaluator avoids a new search by accepting only locked Candidates and one pre-declared mixture. It still cannot make reused data fresh. Its JSON therefore labels the result `descriptive_reused_history` and `fresh_out_of_sample: false`.

## Authoritative July 2026 read

The first proper run used:

- trend: `20260709T232701314885Z_atalanta_trend_buy_hold_spread`, resolved Candidate `cand_06c97170c6d94d2d5eef398a58c050b1`;
- carry: `20260713T200047206608Z_demeter_eu_credit_bucket_yield`, resolved Candidate `cand_7c476e31738759cb2d7344adac904b0e`;
- complete common months: September 2020 through June 2026, `n=70`;
- fixed monthly weights: `60%` trend, `40%` carry;
- MPPM risk aversion: `3`;
- paired circular bootstrap: `2,000` samples at block lengths `1`, `3` and `6` months.

| Measure | Trend only | 60/40 composite | Delta |
| --- | ---: | ---: | ---: |
| Annualized return | 14.19% | 10.29% | -3.90 pp |
| Annualized volatility | 10.32% | 6.65% | -3.67 pp |
| Sharpe | 1.34 | 1.51 | +0.17 |
| MPPM certainty equivalent | 12.28% | 9.37% | -2.91 pp |
| Maximum drawdown | -10.47% | -4.79% | +5.68 pp |
| Worst month | -7.08% | -3.36% | +3.72 pp |
| Skew | 1.13 | 0.78 | -0.34 |

Carry's full-sample correlation to trend was `0.004`. Its correlation in trend's seven worst-decile months was `-0.814`, while its mean return in those months was approximately flat at `-0.025%`. This is unusually helpful dependence, but seven conditional observations are too few for a promotion claim.

All six primary bootstrap intervals included zero:

| Block | 95% MPPM-delta interval | 95% Sharpe-delta interval |
| ---: | ---: | ---: |
| 1 month | [-6.54%, +0.56%] | [-0.19, +0.51] |
| 3 months | [-6.89%, +1.18%] | [-0.22, +0.51] |
| 6 months | [-6.93%, +1.19%] | [-0.25, +0.46] |

> [!warning] Interpretation
> The locked credit candidate is diversifying and drawdown-reducing beside locked Atalanta on this history, but it sacrifices return and lowers the power-utility certainty equivalent. Neither the CE loss nor the Sharpe gain is stable enough to exclude zero under the paired block sensitivities. Retain it as a `credit_income` challenger; do not claim that this run establishes the floor's missing concave pole.

The next valid evidence is a genuinely later common period after both locks, or a pre-registered historical comparison whose candidate choice was frozen before its evaluation window. Re-running weights, risk aversion or block lengths until a preferred answer appears would convert this diagnostic into another model search.

## Sources

[^demiguel]: DeMiguel, Garlappi & Uppal, "Optimal Versus Naive Diversification: How Inefficient Is the 1/N Portfolio Strategy?", *Review of Financial Studies* 22(5), 2009. Evaluates out-of-sample Sharpe, certainty-equivalent return and turnover under estimation error. https://doi.org/10.1093/rfs/hhm075
[^gisw]: Goetzmann, Ingersoll, Spiegel & Welch, "Portfolio Performance Manipulation and Manipulation-Proof Performance Measures", *Review of Financial Studies* 20(5), 2007. Derives a power-utility, continuously compounded manipulation-proof performance measure. https://repec.som.yale.edu/icfpub/publications/2471.pdf
[^ledoitwolf]: Ledoit & Wolf, "Robust Performance Hypothesis Testing with the Sharpe Ratio", *Journal of Empirical Finance* 15, 2008. Recommends studentized time-series bootstrap confidence intervals and joint circular-block resampling of paired strategy returns. http://www.ledoit.net/jef_2008pdf.pdf
[^pw]: Politis & White, "Automatic Block-Length Selection for the Dependent Bootstrap", *Econometric Reviews* 23(1), 2004. Provides data-dependent block-length estimators for stationary and circular bootstraps. https://public.econ.duke.edu/~ap172/Politis_White_2004.pdf
[^ppw]: Patton, Politis & White, "Correction to Automatic Block-Length Selection for the Dependent Bootstrap", *Econometric Reviews* 28(4), 2009. Corrects the optimal block-size formulas. https://public.econ.duke.edu/~ap172/Patton_Politis_White_2009.pdf
[^white]: White, "A Reality Check for Data Snooping", *Econometrica* 68(5), 2000. Shows why inference on a best model must account for repeated specification search and data reuse. https://www.ssc.wisc.edu/~bhansen/718/White2000.pdf

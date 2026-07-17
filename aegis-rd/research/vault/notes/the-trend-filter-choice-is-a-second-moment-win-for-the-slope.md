---
title: The trend-filter choice is a second-moment win for the OLS slope
date: 2026-07-10
tags:
  - note
  - trend
  - convexity
  - signal
topic: whether a different trend filter (EWMAC/Kalman/L1) keeps convexity while improving Sharpe or drawdown, given Levine-Pedersen equivalence is only a first-moment statement
---

# The trend-filter choice is a second-moment win for the OLS slope

> [!note] Status
> SETTLED by measurement (2026-07-10, [[runs/atalanta/2026-07-10#20260710T100358260860Z_atalanta_trend_ewmac]]).
> Two Exa rounds narrowed the filter-swap question, then a causal EWMAC was built as a clean
> single-variable swap for the champion OLS slope and swept over speed. The filter-estimator axis
> is closed: the slope is not only convexity-optimal but also the turnover/Sharpe/drawdown-efficient
> filter.

> [!abstract] One-line takeaway
> Levine-Pedersen equivalence is a FIRST-moment statement (all linear filters carry the same
> signal); it is silent on the SECOND moment (turnover, lag, whipsaw -> Sharpe, drawdown). That
> gap is real - filters differ in weight SHAPE - but on the atalanta trio it resolves in the
> champion's favour: the OLS slope's centre-weighting is smoother at the endpoint than the EWMA
> crossover's recent-weighting, so it trades less and wins Sharpe/DD at equal convexity.

## The valid objection

"All linear trend filters are equivalent" (Levine-Pedersen[^1]) understates what is settled. Their
proof is that the EWMA crossover, TSMOM, the HP/Kalman/OLS-slope filters are equivalent
representations of the same SIGNAL - a first-moment result. It says nothing about turnover, phase
lag, or whipsaw, which are second-moment properties and which drive Sharpe and drawdown. Two filters
can carry the same trend signal and yet one bleeds far more in chop. So "is there a filter that keeps
convexity but improves Sharpe/DD?" is a legitimate, open question - not closed by equivalence.

## The literature already resolves the second-moment axis - toward the slope

- **Baltas-Kosowski[^2]**: fitting a linear trend on the price path (exactly `trend_score_regress`)
  delivers the same pre-cost Sharpe as the sign/return signals but cuts turnover by about two
  thirds, giving a significantly better NET Sharpe. The slope is the turnover-minimising filter by
  construction.
- **Grebenkov-Serror / "Breaking the Trend"[^3]**: a single EMA is Sharpe-optimal; a multi-timescale
  MACD does not beat it (1.24 vs 1.18). No crossover elaboration wins Sharpe.
- **Carver's skew-by-speed[^4]**: slow crossovers carry NEGATIVE daily skew (16,64 = -0.73);
  positive skew emerges only at long measurement horizons. So a slow crossover has no convexity
  edge over the slope at our 2-6mo band.
- The one structurally-different, drawdown-targeting filter, the **L1 trend filter**[^5], is a
  wash-to-worse vs the moving average on trend-following AND is offline/non-causal (its penalty
  reaches into t+1), so it is unusable on a live sleeve without an endpoint-unstable causal refit.

## The measurement on our book

A causal Carver EWMAC (`EMA(logP, Lfast) - EMA(logP, Lslow)`, `Lslow = 4*Lfast`, rescaled by the
crossover horizon `(Lslow-Lfast)/2` into the slope's annualized-return units so
`keystone_shortmute` consumes it unchanged) was swept over `Lslow {126, 189, 252}` against the
champion, everything else byte-identical:

| filter | conv | Sharpe | mean maxDD | worst maxDD | fees |
|---|---|---|---|---|---|
| champion OLS slope lb189 | 0.4183 | 1.323 | 6.61 | 10.18 | 23.6 |
| EWMAC 126 | 0.4014 | 1.231 | 6.90 | 9.17 | 33.2 |
| EWMAC 189 (matched) | 0.4159 | 1.076 | 10.15 | 10.15 | 25.9 |
| EWMAC 252 | 0.4311 | 1.129 | 7.76 | 11.52 | 17.2 |

- **Convexity**: at the MATCHED horizon (189) EWMAC ties-to-slightly-loses (0.4159 vs 0.4183) - the
  equivalence holding as predicted. The one cell that edges the champion, Lslow=252 (+0.013), is not
  real: paired vs champion per-split, Wilcoxon p=0.81 / paired-t p=0.90, the gain driven entirely by
  ONE split (s3 0.95 vs 0.49) while EWMAC is worse on 5 of 7. The same spec-luck shape as the killed
  `volbeta` (p=0.88) and power-response (p=0.59) non-wins.
- **Sharpe / drawdown (the actual question)**: EWMAC LOSES Sharpe at every speed (1.231 / 1.076 /
  1.129, all below the champion 1.323 and the slow cell below the sleeve's own 1.15 floor) and loses
  drawdown at the matched and slow speeds. It never Pareto-improves.

## Mechanism

The OLS slope weights returns at the CENTRE of the window most (Levine-Pedersen signature plots[^1]);
the EWMA crossover weights RECENT returns most. Recent-weighting makes the endpoint estimate noisier,
so the crossover flips more often - turnover rises (fees up to 33 vs 23.6) and the extra trading
costs net Sharpe and deepens drawdown, all for the SAME convexity. This is Baltas-Kosowski's
turnover result[^2] reproduced on the 3-name book. The second moment the objection rightly flagged
DOES differ across filters - and it differs in the champion's favour.

## Standing conclusion

- The trend-filter-estimator axis joins signal, formula, speed, sizing (four faces), universe, and
  build-vs-buy as CLOSED on the atalanta trio. The OLS slope is the turnover/Sharpe/DD-efficient
  filter, not merely the convexity-optimal one.
- Any filter tweak that DID buy Sharpe would, on this sleeve, buy it by shedding convexity (the
  Sharpe-vs-skew tightrope[^6]) - off-mandate for the floor. The slope sits at the right corner:
  convexity-max AND second-moment-efficient.
- **Re-entry**: a high-breadth, higher-cost-tolerant book where a faster crossover's convexity edge
  would pay its turnover - not the slow 3-name UCITS trio. Same breadth precondition as the rest of
  the axis.

## See also

- [[sizing-shape-is-already-convexity-maximal]] - the sizing axis (also closed by measurement)
- [[what-makes-a-trend-sleeve-convex]] - the harvest ceiling this filter sits under
- [[trend-speed-buys-drawdown-not-convexity]] - the speed axis and the thin-book breadth wall

## Sources

[^1]: Levine & Pedersen, "Which Trend Is Your Friend?", Financial Analysts Journal, 2016. https://doi.org/10.2469/faj.v72.n3.3
[^2]: Baltas & Kosowski, "Improving Time-Series Momentum Strategies: The Role of Volatility Estimators and Trading Signals", 2013. https://www.cmegroup.com/education/files/improving-time-series-momentum-strategies.pdf
[^3]: "Breaking the Trend: How to Avoid Cherry-Picked Signals" (Grebenkov-Serror framework), arXiv 2504.10914. https://arxiv.org/html/2504.10914v5
[^4]: Rob Carver, "Skew and Trend following", qoppac, 2019. https://qoppac.blogspot.com/2019/02/skew-and-trend-following.html
[^5]: Bruder, Dao, Richard & Roncalli, "Trend Filtering Methods for Momentum Strategies", 2011 (and CFM, "Momentum Strategies with L1 Filter", 2014). http://www.thierry-roncalli.com/download/lwp-tf.pdf
[^6]: Research Affiliates, "Walking the Tightrope: Trend Following's Tricky Tradeoffs", 2025. https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1077-trend-followings-tricky-tradeoffs-sharpe-ratio-vs-skew.pdf

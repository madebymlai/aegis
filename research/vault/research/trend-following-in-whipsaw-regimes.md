---
title: Trend-Following in Whipsaw Regimes
date: 2026-06-10
topic: trend-following
distilled-into:
tags:
  - article
---

# Trend-Following in Whipsaw Regimes

> [!abstract] One-line takeaway
> A trend sleeve's losses in choppy, trendless years are not a fixable defect but the premium it pays for crash-time convexity; the evidence says you cannot filter your way out of whipsaw, only diversify trend speed and control drawdown.

Every trend-follower bleeds in range-bound markets, and the instinct is to add a filter that switches the strategy off when no trend is present. The literature is unusually clear that this instinct is mostly wrong: the bleed is structural, the filters that promise to remove it are lagging and overfit, and the strongest neutral evidence says the bad years are caused by something no filter can manufacture - the absence of large market moves. What *does* survive out-of-sample is narrower and less satisfying: diversify across trend speeds so turning points hurt less, and use volatility scaling for drawdown control rather than as a source of chop-year alpha. This article separates the two.

## Whipsaw is the price of convexity, not a bug

A trend rule is mechanically a delta-replicated long straddle. Fung and Hsieh showed that a primitive trend-following strategy has the payoff of a lookback straddle - it earns the maximum-minus-minimum price travel over its window - which is why trend returns are long-volatility and largest in the most extreme up *and* down months.[^funghsieh] Bruder and Gaussel decompose the same payoff into an option component (the convexity) plus a trading-impact component (a premium proportional to the underlying's Sharpe), making explicit that the convex profile is bought, not free.[^bruder] The cost of that option is whipsaw: a strategy that scales into moves and out of reversals must repeatedly pay up at every reversal that fails to become a trend.

The deeper mechanism is autocorrelation. Moskowitz, Ooi and Pedersen show time-series momentum is driven by positive return autocorrelation at horizons of one to twelve months, partially reversing thereafter.[^mop] When a market goes trendless, that autocorrelation collapses toward zero or turns negative, and every entry sits on the wrong side of the next move. This matters for diagnosis: the chop-year bleed is a *reversal-sign* problem, not a *weak-trend-strength* problem. Raising a trend-strength threshold filters out weak-but-real trends while doing nothing about reversals at regime transitions, which is precisely where the losses concentrate. A strategy can be holding assets with perfectly adequate trend strength and still be whipsawed as those trends turn.

## The filter trap

The popular regime filters - Kaufman's Efficiency Ratio, ADX, the Hurst exponent - all share two disqualifying properties. They are *lagging*: the Efficiency Ratio and Hurst exponent describe what a window has already done, not what it will do next, so they flag a chop regime only after the whipsaw losses have been taken.[^kaufman][^hurst] And they carry *no out-of-sample validation*: the published performance figures for efficiency-ratio or Hurst-gated systems are blog-grade and uncontrolled, with no peer-reviewed evidence that a standalone range filter improves a diversified trend book. The structural trade-off is that gating out low-efficiency tape forfeits trend capture during weak-but-real trends about as often as it saves losses in genuine chop.

The strongest neutral evidence against the filter instinct is AQR's "You Can't Always Trend When You Want."[^aqrtrend] Analysing post-crisis trend underperformance, they find it is explained by the average absolute size of market moves being unusually muted, not by any decline in trend's ability to convert moves into returns - the relationship between move size and trend's risk-adjusted return is positive and stable. The implication is blunt: if the bleed is the absence of large moves, no efficiency-ratio or Hurst gate can create trend that is not there, and filtering only sacrifices the convex payoff for when moves return. That this argument comes from a firm running trend funds (which has an interest in "stay invested") is a conflict, but the argument cuts *against* the easy-fix narrative its own filters could sell, which strengthens rather than weakens it.

## What survives out of sample: speed diversification

The one fix with genuine peer-reviewed support is diversifying across trend speeds. Garg, Goulding, Harvey and Mazzoleni show that an intermediate blend of fast and slow signals earns a Sharpe of 1.12 against 0.87 for fast-only and 0.81 for slow-only, and - directly relevant to whipsaw - that *disagreement* between fast and slow signals is itself a turning-point warning, the moment when reversal risk is highest.[^garg] Blending speeds smooths the equity curve through exactly the regime transitions that whipsaw a single-speed system.

The nuance is that more speeds is not more diversification. Recent work shows adjacent lookbacks are highly redundant - 125-day and 250-day signals correlate around 0.84, 250-day and 500-day around 0.90 - so a "barbell" of one short and one well-separated long horizon captures nearly all the benefit, and a dense ladder of intermediate lookbacks adds almost nothing once the short and long legs are present.[^barbell] The actionable form of the fix is two well-separated speeds, not a stack of them.

## Volatility scaling is drawdown control, not chop-alpha

Volatility targeting is often proposed as a chop remedy, and the evidence asks for care. Harvey and co-authors find that vol-scaling raises the Sharpe ratio only for equity-like and credit assets, through the leverage effect (volatility and returns are negatively related there), and that the Sharpe benefit is negligible for bonds, currencies, and commodities.[^harveyvol] For a trend sleeve that is mostly *not* equity, the robust benefit of vol-scaling is therefore not higher Sharpe but lower tail risk - reduced vol-of-vol, kurtosis, and drawdowns. And the broader vol-timing claim is OOS-fragile: Moreira and Muir's in-sample finding that scaling down in high-vol periods raises alpha[^moreiramuir] is contradicted out-of-sample by Cederburg and co-authors, who find real-time vol-managed portfolios generally earn *lower* certainty-equivalent returns and Sharpe ratios than simply holding the unmanaged portfolio.[^cederburg] Use vol-scaling to control drawdown, and do not expect it to pay for the chop.

Two weaker levers round out the menu. Cross-asset *breadth or dispersion* gates - throttling exposure by how many instruments are genuinely trending - are plausible and correlate with trend performance, but the supporting evidence is thin and largely CTA-sourced, so they are research-grade rather than established. And *signal smoothing* via a saturating response function reduces turnover and therefore the transaction-cost share of the whipsaw bill,[^baz] but it does not restore the missing autocorrelation; it makes whipsaw cheaper, not rarer.

## Limitations

- The "filters overfit" conclusion rests partly on an *absence* of evidence (no peer-reviewed study shows efficiency-ratio or Hurst gates work OOS) plus AQR's muted-moves argument; it is well-motivated but not a single clean disproof. Confidence: medium-high.
- Speed-blending's benefit is well-supported (two independent sources), but the figures come from broad futures universes; the magnitude in a thin equity-ETF book is unverified.
- Vol-scaling's asset-class dependence and OOS fragility are strongly sourced (Harvey plus Cederburg); the breadth-gate lever is genuinely uncertain and flagged as such.

## Strategy hypotheses this could seed

- [ ] A two-speed barbell (one short, one well-separated long lookback) blended in the trend core reduces turning-point/whipsaw bleed in trendless years without flattening crash-time convexity - the best-evidenced fix.
- [ ] Throttling gross exposure by trend breadth (count of instruments past the entry band) cuts the chop bleed - test, but pre-register as research-grade given thin evidence.
- [ ] A cross-sectional or vol-regime gross throttle reduces drawdown in chop but does *not* improve Sharpe - confirm vol-scaling is a drawdown tool, not a chop-alpha tool.
- [ ] No standalone regime filter (efficiency ratio / strength threshold) beats simply diversifying trend speed - the AQR null, worth confirming directly since the campaign already killed one trend-gate.

## Sources

[^funghsieh]: Fung, W. & Hsieh, D., "The Risk in Hedge Fund Strategies: Theory and Evidence from Trend Followers", Review of Financial Studies 14(2):313-341, 2001. https://people.duke.edu/~dah7/TheRiskinHedgeFundStrategies.pdf
[^bruder]: Bruder, B. & Gaussel, N., "Risk-Return Analysis of Dynamic Investment Strategies", SSRN, 2011; summarised in Newfound Research, "Trend: Convexity & Premium", 2019. Trend payoff = option (convexity) + trading impact (premium proportional to asset Sharpe). https://blog.thinknewfound.com/2019/02/trend-convexity-premium/
[^mop]: Moskowitz, T., Ooi, Y. & Pedersen, L., "Time Series Momentum", Journal of Financial Economics 104(2):228-250, 2012. Driven by positive return autocorrelation at 1-12 months; AQR-affiliated authors. https://elmwealth.com/wp-content/uploads/2017/06/timeseriesmomentum.pdf
[^kaufman]: Kaufman, P., Efficiency Ratio / Kaufman's Adaptive Moving Average (definition via StockCharts ChartSchool). ER = directional move / sum of absolute moves; lagging, no peer-reviewed OOS performance evidence. https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama
[^hurst]: Macrosynergy, "Detecting trends and mean reversion with the Hurst exponent". H>0.5 trending, H<0.5 mean-reverting; explicitly lagging, a meta-filter not a signal. https://macrosynergy.com/research/detecting-trends-and-mean-reversion-with-the-hurst-exponent/
[^aqrtrend]: Babu, A., Hoffman, B., Levine, A., Ooi, Y., Schroeder, S. & Stamelos, E. (AQR), "You Can't Always Trend When You Want", Journal of Portfolio Management 46(4):52-68, 2020. Trend's weak years are driven by muted average market-move size, not filterable regimes. AQR runs trend funds (COI), but the argument cuts against the easy-fix narrative. https://jpm.pm-research.com/content/46/4/52
[^garg]: Garg, A., Goulding, C., Harvey, C. & Mazzoleni, M., "Momentum Turning Points", Journal of Financial Economics, 2023. Intermediate fast/slow blend Sharpe 1.12 vs 0.87 (fast) and 0.81 (slow); fast-slow disagreement flags turning points. https://www.sciencedirect.com/science/article/abs/pii/S0304405X23001034
[^barbell]: "Revisiting the Structure of Trend Premia: When Diversification Hides Redundancy", arXiv:2510.23150, 2025. Adjacent lookbacks correlate 0.84-0.90; optimal allocation is a short+long barbell, intermediate horizons get near-zero weight. https://arxiv.org/html/2510.23150v2
[^harveyvol]: Harvey, C., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M. & Van Hemert, O., "The Impact of Volatility Targeting", Journal of Portfolio Management, Fall 2018. Vol-scaling raises Sharpe only for equity/credit (leverage effect), negligible for bonds/FX/commodities; main robust benefit is tail/drawdown reduction. Man Group authors (COI). https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
[^moreiramuir]: Moreira, A. & Muir, T., "Volatility-Managed Portfolios", Journal of Finance 72(4):1611-1644, 2017. In-sample, scaling down in high-vol periods raises Sharpe and alpha. https://amoreira2.github.io/alan-moreira.github.io/VolPortfolios_published.pdf
[^cederburg]: Cederburg, S., O'Doherty, M., Wang, F. & Yang, X., "On the performance of volatility-managed portfolios", Journal of Financial Economics, 2020. Out-of-sample vol-managed portfolios generally earn lower certainty-equivalent return and Sharpe than buy-and-hold. https://www.lehigh.edu/~xuy219/research/COWY.pdf
[^baz]: Baz, J., Granger, N., Harvey, C., Le Roux, N. & Rattray, S., "Dissecting Investment Strategies in the Cross Section and Time Series", SSRN, 2015. Canonical reference for signal smoothing / response functions to dampen turnover. Man/AHL authors (COI). https://www.cmegroup.com/education/files/dissecting-investment-strategies-in-the-cross-section-and-time-series.pdf

---
title: Measuring Crisis Alpha
date: 2026-06-10
topic: performance-measurement
distilled-into:
tags:
  - article
---

# Measuring Crisis Alpha

> [!abstract] One-line takeaway
> Full-sample Sharpe rewards calm-market smoothness; to rank a sleeve on stress responsiveness use a drawdown-aware objective (Ulcer Performance Index or moderate-alpha CDaR), and reward actual crash gains only through capture or multi-window measures - never by optimising on a single worst episode.

A ranking metric is a statement about what you want. Full-sample Sharpe says "high average return per unit of average volatility," which is satisfied best by a strategy that is smooth in the years that dominate the sample - the calm ones. A sleeve whose entire purpose is to gain during rare equity crashes is therefore systematically *mis*-ranked by Sharpe: its crash-time payoff is a few percent of the observations, swamped by the bleed it pays the rest of the time. Selecting such a sleeve needs an objective that weights the stress windows more heavily. The catch is that the metrics which most directly reward crash performance are also the most fragile, because crashes are rare and the relevant statistics are dominated by single paths. This article lays out the menu and argues for the robust middle.

## What the candidate metrics actually reward

The drawdown-aware family measures the shape of the equity curve's underwater periods rather than its return volatility. The **Ulcer Index** is the root-mean-square of percentage drawdowns from the running peak, so it penalises both the depth and the *duration* of being underwater, and squaring means deep dips are punished harder than shallow ones; the **Ulcer Performance Index** (Martin ratio) divides excess return by it.[^ulcer] **Conditional Drawdown at Risk** generalises this: it is the mean of the worst (1-alpha) fraction of drawdowns, tunable from average drawdown (alpha near 0) to maximum drawdown (alpha near 1), and it is convex and tractable for optimisation.[^cdar] The classic ratios - **Calmar/MAR** (return over maximum drawdown), **Sterling**, **Burke** - sit at the fragile end because they lean on the single worst decline.[^bacon]

The downside-risk family conditions on a return threshold. The **Sortino ratio** divides excess return by downside deviation, the volatility of returns below a minimum acceptable return, so it rewards strategies whose downside is small - but its ranking shifts with the arbitrary threshold choice.[^sortino] **Conditional Value at Risk** (expected shortfall) is the mean loss in the worst (1-alpha) tail, a coherent risk measure that is linear-programming tractable.[^cvar] Neither directly rewards *gaining* in a crash; they reward losing little.

The conditional family is the only one that rewards crash gains directly. **Up- and down-capture ratios** measure a sleeve's compounded return in the benchmark's up and down months as a fraction of the benchmark's - a defensive sleeve wants down-capture below 100, and a true crisis-alpha sleeve wants it *negative* (it gains when the benchmark falls).[^capture] The **stress-window conditional return**, the "crisis alpha" of Greyserman and Kaminski, is simply performance measured inside defined equity-crash windows.[^kaminski] This is the thing we actually want - but it is also the most exposed to the central pitfall.

## The pitfall: rare crashes make the best-aimed metrics the least stable

The metrics that most directly target crash performance are single-path order statistics over a handful of events, and they do not generalise. Magdon-Ismail and Atiya derive the expected maximum drawdown for Brownian motion with drift and show it grows with the length of the track record and carries large sampling error - so a backtested maximum drawdown (and any Calmar or MAR built on it) is a biased, noisy number, and optimising a ranking objective directly on it overfits to the one worst historical episode.[^magdon] The tail measures fail the same way from the other direction: Varga-Haszonits and Kondor prove that the estimation error of VaR, expected shortfall, and semivariance *diverges* as the sample size approaches the number of parameters, so CVaR-based optimisation is unstable precisely when crash data is scarce.[^vargakondor] A stress-window conditional return computed over three or four crashes is the limiting case - it is exactly as overfit as the number of windows is small.

This is the crux for designing a ranking objective. The closer a metric gets to "did you make money in *this* crash," the more it rewards a candidate for fitting that crash's idiosyncrasies. With only a few crash episodes in any realistic sample, optimising on the sharpest crisis metric selects for luck on those specific episodes, not for a repeatable crash-time edge.

## The robust middle

The resolution is to rank on a metric that integrates the whole equity curve while still rewarding shallow, short drawdowns, and to bring in the direct crash-gain signal only in regularised form. Two properties separate the robust objectives from the fragile ones: they use *many* observations rather than one path, and they have no arbitrary threshold. By that test the **Ulcer Performance Index** and **CDaR at moderate alpha** (roughly 0.05 to 0.2) are the best smooth, stress-aware ranking objectives - both reward crisis shallowness without collapsing onto the single-path maximum drawdown, and both are well-behaved for optimisation.[^ulcer][^cdar] To additionally reward *gaining* in stress rather than merely losing little, blend in a **down-capture** term or a **multi-window** conditional return averaged or bootstrapped across many stress windows - never a single one.[^capture][^kaminski] What to avoid as a direct optimisation target is the fragile end: raw Calmar/MAR and any single-window crisis return, which the sampling-error results show will not generalise.[^magdon][^vargakondor]

## Limitations

- The Ulcer Index primary source (Martin and McCann, 1989) could not be retrieved directly; the formula is verified across independent secondary sources and is not in dispute, but the grade on the primary is capped.
- The sample-dependence pitfall is strongly established for maximum drawdown and for CVaR by two independent peer-reviewed sources; the claim that it extends to a few-window crisis return is our own extrapolation from the same statistics, not a separately published result.
- These are *ranking* arguments. Which metric, in our data and splits, actually selects more stress-responsive candidates than Sharpe is an empirical question this article only frames.

## Strategy hypotheses this could seed

- [x] Ranking candidates on the Ulcer Performance Index instead of full-sample Sharpe selects sleeves with shallower crash-window drawdowns at acceptable full-sample cost - the first custom ranking Metric to register. **Supported 2026-06-10**: on the identical crisis-blend grid, UPI ranking selected a different candidate (heavier trend core, slower vol window) with shallower held-out drawdowns (5.54% vs 5.74% mean max_dd) at zero Sharpe cost (+1.007 vs +1.008) - and, as predicted, traded crash-time gain (2022 +0.47 vs +0.82) for smoothness. Registered as the opt-in `ulcer_performance_index` Metric. See [[runs/aegis/2026-06-10|run diary]].
- [ ] A CDaR-at-moderate-alpha ranking objective selects similar candidates to UPI (robustness cross-check), while Calmar/MAR selects visibly more overfit ones - confirm the fragile-vs-robust split on our data.
- [ ] A down-capture or multi-window conditional-return term, regularised across all in-sample stress windows, shifts selection toward sleeves that *gain* in crashes rather than merely lose little - the metric closest to the allocator's true objective.
- [ ] Optimising directly on a single-window (e.g. 2022-only) crisis return overfits and degrades on held-out crashes - the pre-registered negative control.

## Sources

[^ulcer]: Martin, P. & McCann, B., The Investor's Guide to Fidelity Funds, 1989 (Ulcer Index introduced 1987). UI = root-mean-square of percentage drawdowns from the running peak; UPI (Martin ratio) = excess return / UI. Formula verified via StockCharts and secondary references. http://www.tangotools.com/ui/ui.htm
[^cdar]: Chekhlov, A., Uryasev, S. & Zabarankin, M., "Drawdown Measure in Portfolio Optimization", International Journal of Theoretical and Applied Finance 8(1):13-58, 2005. CDaR = mean of the worst (1-alpha) drawdowns; alpha near 0 gives average drawdown, alpha near 1 gives maximum drawdown; convex and optimisation-tractable. https://www.cis.upenn.edu/~mkearns/finread/drawdown.pdf
[^bacon]: Bacon, C., Practical Portfolio Performance Measurement and Attribution, Wiley. Standard definitional reference for Calmar/MAR, Sterling, Burke, Martin/UPI, and Pain ratios. https://www.wiley.com/en-us/Practical+Portfolio+Performance+Measurement+and+Attribution
[^sortino]: Sortino, F. & van der Meer, R., "Downside Risk", Journal of Portfolio Management, 1991. Sortino ratio = (return - MAR) / downside deviation; downside deviation uses only returns below the minimum acceptable return; sensitive to the MAR choice. https://en.wikipedia.org/wiki/Sortino_ratio
[^cvar]: Rockafellar, R. T. & Uryasev, S., "Optimization of Conditional Value-at-Risk", Journal of Risk 2:21-41, 2000. CVaR / expected shortfall = mean loss in the worst (1-alpha) tail; a coherent risk measure, LP-tractable via an auxiliary function. https://www.financerisks.com/filedati/WP/paper/CVaR%20Portfolio%20Optimization.pdf
[^capture]: Up/Down Capture ratios (Morningstar methodology). Down-capture = compounded fund return in benchmark-down months / compounded benchmark return in those months x 100; below 100 is defensive, negative means gaining when the benchmark falls. https://ycharts.com/glossary/terms/upside_downside_ratio
[^kaminski]: Greyserman, A. & Kaminski, K., Trend Following with Managed Futures: The Search for Crisis Alpha, Wiley, 2014. Crisis alpha = conditional performance measured inside equity-crash windows. Authors run/advise trend funds (COI); the conditional-window definition is the load-bearing idea. https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/trend-following-with-managed-futures
[^magdon]: Magdon-Ismail, M. & Atiya, A., "An Analysis of the Maximum Drawdown Risk Measure", Risk, 2004. Expected maximum drawdown for Brownian motion with drift grows with track-record length and carries large sampling error; optimising on it overfits the single worst episode. https://www.cs.rpi.edu/~magdon/ps/journal/drawdown_RISK04.pdf
[^vargakondor]: Varga-Haszonits, I. & Kondor, I., "The instability of downside risk measures", arXiv:0811.0800, 2008. Estimation error of VaR, expected shortfall, and semivariance diverges as sample size approaches the parameter count; CVaR optimisation is unstable when tail data is scarce. https://arxiv.org/abs/0811.0800

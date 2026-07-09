---
title: Trend speed buys (a little) drawdown, not convexity, on a thin book
date: 2026-07-09
tags:
  - note
  - trend
  - convexity
topic: whether a fast/short trend horizon lifts convexity or cuts drawdown on the atalanta trio
---

# Trend speed buys (a little) drawdown, not convexity, on a thin book

> [!note] Status
> TESTED and settled on our book (2026-07-09). An earlier draft of this note claimed the
> fast-horizon lever was "unrun" - that was WRONG: it had been run twice before (in flawed
> constructions), and has now been run a third time in the CORRECT construction with a
> bit-for-bit champion anchor. All three agree. This note records the reconciliation of
> "the literature says fast buys convexity" vs "our thin book says it dilutes convexity".

> [!abstract] One-line takeaway
> The broad-futures result - that a short/fast horizon supplies crisis convexity and
> turning-point tail-truncation - does NOT transfer to the thin 3-ETF atalanta trio: here a
> fast leg dilutes convexity monotonically and, at best, mildly patches one reversal split.
> Above the harvest ceiling (0.447) you must BUY gamma (tail sleeve), not harvest faster.

## What the literature says (correct, and still worth keeping)

Five sources, three of them 2023-2025, place crisis convexity and turning-point drawdown
protection at the SHORT/FAST end of the trend spectrum:

- **Man AHL "Need for Speed" (2023)**: skewness/convexity/worst-quintile crisis alpha
  INCREASE with speed; faster models "truncate the reversal left tail"; the slowest speed
  "cannot shift short over a one-to-three-month horizon" (why slow trend missed COVID).[^1]
- **Goulding-Harvey-Mazzoleni "Momentum Turning Points" (JFE 2023)** and the follow-on
  **"Breaking Bad Trends" (FAJ 2023)**: turning points are TSMOM's Achilles heel; the union
  of a slow and a fast signal DETECTS them (signs disagree = turning point), and blending /
  de-risking there gives "less severe drawdowns" and skew shifted positive.[^3]
- **arXiv 2510.23150 (Oct 2025) barbell**: optimal config is short+long, medium redundant;
  the 20-day sleeve carries "meaningful crisis convexity."[^4]

The intended mechanics matter for construction:
- **Combine at the SIGNAL level** (one blended score -> one book). A rebalanced AVERAGE of two
  weight books is a rebalancing-premium CONCAVE payoff and destroys convexity (ThinkNewfound).[^6]
- GHM use a fast signal as a turning-point MODULATOR (scale down on disagreement), not a fast
  trading leg.

## What our book actually does (three tests, all agree)

The atalanta champion is a SINGLE slow OLS-slope horizon (lb189) -> keystone_shortmute on
IDTL/IGLN/ICOM. The fast lever has now been tested three ways:

1. **Fast trading leg / averaged barbell** - killed 2026-06-10 (aegis 10-ETF): "the fast leg
   added whipsaw instead of dampening turning points; the broad-futures speed result did not
   transfer." Construction flaw: this was the concave weight-AVERAGE form, wrong book, long-only.
2. **Turngate (fast as disagreement modulator, GHM)** - killed 2026-06-29: held-out convexity
   falls monotonically with gate strength (0.424 -> 0.401 -> 0.358); it DID cut the worst
   reversal split (-5.35% -> -2.81%, that split's maxDD 13.45 -> 9.61) but forfeited convex
   capture on false-positive mid-trend pullbacks. Construction caveat: tested on the
   pre-short-cap champion (0.424), not today's locked 0.447.
3. **Signal-level additive barbell (the CORRECT construction)** - killed 2026-07-09,
   [[runs/atalanta/2026-07-09]]. Blend `(1-w)*slope189 + w*slope30_rescaled` -> the UNCHANGED
   current champion; fast leg vol-rescaled so bands/short-cap stay calibrated;
   **blend_w=0 reproduces the champion 0.4451 bit-for-bit** (clean anchor). Result:

   | blend_w | held-out conv | mean maxDD | worst-split maxDD | reversal split conv/ret |
   |---|---|---|---|---|
   | 0.00 (champion) | 0.4451 | 7.28 | 10.18 | 0.024 / -3.05% |
   | 0.15 | 0.4346 | 7.44 | 10.28 | 0.087 / -1.90% |
   | 0.30 | 0.4099 | 7.73 | 9.89 | -0.048 / -6.38% |

   Convexity falls MONOTONICALLY, no bulge; the pure champion is the convexity-max; Friedman
   p~0.39 (cells indistinguishable). A small dose (w=0.15) mildly patches the worst reversal
   split but taxes convex capture on every trending split, so the net is down. Drawdown NOT
   improved to bar (mean maxDD worsens; worst-split misses champion-1pp; calm-year floor breaks
   at w=0.30). Same shape as the turngate, now on the correct construction and current champion.

## Why the transfer fails (the reconciliation)

On a broad short-able futures book (50+ markets), a fast leg has BREADTH: some markets turn
while others trend, so the fast signal's turning-point catches net positive and its whipsaw
diversifies away. On a thin 3-name correlated macro trio, there is no breadth to diversify the
fast leg's whipsaw, and the same fast signal that catches the one true reversal also de-risks
every healthy mid-trend pullback (false positives), forfeiting the convex capture that IS the
sleeve's job. This is the "can't filter/blend your way out" null - now reproduced **5 times** on
this book (fast leg, turngate, R^2 proxy, ER gate, additive barbell).

## The standing conclusion

- The convexity ceiling **0.447 is the HARVEST ceiling** - the most gamma a dynamic slow-trend
  book on this trio can harvest for free. Exceeding it requires **BOUGHT** gamma (options /
  long-vol), which is the tail sleeve's mechanism ([[the-ucits-constrained-tail-sleeve]]), pays
  at fast crashes, and bleeds on slow chop - so it belongs in a different seat, not atalanta.
- The residual turning-point drawdown (the 2023-type whipsaw) has **no thin-book fix that
  preserves convexity**. Speed cuts it only marginally and at a net convexity cost.
- **Re-entry condition** (what would change the kill): a short-able MULTI-market futures book,
  not the 3-ETF UCITS trio - i.e. a bigger account / different substrate where speed
  diversification has the breadth to work. Same precondition as the whole breadth axis.

## See also

- [[what-makes-a-trend-sleeve-convex]] - the harvest ceiling this pushes on
- [[trend-following-in-whipsaw-regimes]] - the turning-point drawdown
- [[the-orthogonal-non-equity-trend-universe]] - the breadth wall (same precondition)
- [[runs/atalanta/2026-07-09]] - the champion-anchored barbell run; [[runs/atalanta/2026-06-29]] - the turngate

## Sources

[^1]: Man AHL, "The Need for Speed in Trend-Following Strategies", 2023. https://www.man.com/insights/need-for-speed-trend-following
[^3]: Goulding, Harvey, Mazzoleni, "Momentum Turning Points", JFE 149 (2023) 378-406, https://people.duke.edu/~charvey/Research/Published_Papers/P158_Momentum_turning_points.pdf ; Harvey et al., "Breaking Bad Trends", FAJ 2023, https://people.duke.edu/~charvey/Research/Published_Papers/P167_Breaking_bad_trends.pdf
[^4]: "Revisiting the Structure of Trend Premia", arXiv:2510.23150, Oct 2025. https://arxiv.org/html/2510.23150v2
[^6]: Newfound Research, "Ensembles and Rebalancing", 2020. https://blog.thinknewfound.com/2020/02/ensembles-and-rebalancing/

---
title: The sizing shape is already convexity-maximal; the pyramid/response family is a four-kill arc
date: 2026-07-10
tags:
  - note
  - trend
  - convexity
  - sizing
topic: whether a different position-sizing rule (not inverse-vol) unlocks more convexity, and whether it revives the t-stat
---

# The sizing shape is already convexity-maximal; the pyramid/response family is a four-kill arc

> [!note] Status
> SETTLED by measurement (2026-07-10). Two Exa rounds established that the champion already makes
> all four convexity-maximising construction choices; the one lever they left open - a
> super-proportional (pyramiding / convex) response - is now a FOUR-kill arc: extension pyramids
> (FORGO ramp, levered add-on, give-back stop) plus the UNLEVERED power response
> ([[runs/atalanta/2026-07-10]]). The whole sizing axis is closed by the grid, not by prior.

> [!abstract] One-line takeaway
> Trend convexity is MECHANICAL - set by position construction - and the convexity-max construction
> (proportional, uncapped, single-smoother, long vol window) is exactly what the champion already
> does. `return/vol` is the lowest-SKEW normalisation, not the max-convexity one, and the
> convexity-adding direction (less de-risking) was already swept flat ([[inverse-vol-sizing-is-convexity-neutral-here]]).
> The only untested lever - scaling up MORE than proportionally into winners - is minimal at our
> lookback, EV-suboptimal for momentum, drawdown-deepening, and explicitly avoided by the best UCITS CTA.

## The mechanism is unanimous: our shape is already the convex one

Every serious treatment of trend convexity says it is MECHANICAL, produced by position construction,
and maximised by four choices - all of which `keystone_shortmute` already makes:

| Convexity-max rule | Source | Champion |
|---|---|---|
| Position **proportional** to trend (not sign; not `tanh`/capped) | CFM[^1], Dao-Bouchaud[^2] | continuous magnitude (proportional) |
| **Uncapped** ("capping reduces the size of the fat tails") | CFM[^1] | uncapped longs (only the IDTL *short* is capped, for DD) |
| **No extra EMA** on the predictor ("another layer of averaging is detrimental to convexity") | CFM[^1] | single regression-slope smoother |
| **Long** asset-vol window (short window "negates positive skew") | Research Affiliates[^3] | `vol_window = 126` |

CFM/Dao-Bouchaud: `Pi ~ +/-1` (sign) or `tanh(T)` (capped) gives a V-shape; strictly proportional,
uncapped gives the full parabola - "if one continues to build up a position as trends get bigger, one
assumes more risk infrequently - the definition of kurtosis / fat tails." So the champion sits on the
convex end by construction. This is a validation, not a gap.

## Why `return/vol` is not the lever it looks like

Inverse-vol sizing is the LOWEST-skew rule (Kaminski), because it de-risks INTO turbulence. So the
convexity-adding direction is LESS de-risking, not a different denominator - and that end (the vol
exponent -> 0) is `volbeta`, already swept flat (Friedman p=0.88, beta=0 ~= champion). The residual
leak is plugged by the long vol window (RA), not liftable by re-sizing. See
[[inverse-vol-sizing-is-convexity-neutral-here]].

Sizing by the regression RESIDUAL vol (which would make position ~ t(beta), the "t-stat at the sizing
layer") does NOT revive the t-stat: naive residual-vol is the same unit-root-inflated quantity that
made the literal slope-t invalid, and HAC-corrected residual-vol collapses back to ~ `return/vol`.
No free lunch - the pathology lives in the residual variance, not in where it is applied.

## The pyramid/response lever: a four-kill arc

CFM and Concretum[^4] agree the only thing that adds convexity BEYOND proportional is scaling up MORE
than linearly into winners - a convex response function / pyramiding. The clean form is Lopez de
Prado's power sizer[^5] `bet = sign(score) * |score_norm| ** w` (w=1 = linear champion, w>1 = convex).
Concretum quantifies it: Volatility-Parity-plus-Pyramiding lifts Profit Factor 1.48 -> 1.74 and
monthly skew 2.4 -> 3.74.

On our book it is now a FOUR-kill arc, tested from every side:

- **Extension pyramids** (2026-07-03 FORGO ramp, 2026-07-06 levered add-on, 2026-07-07 give-back
  stop): the levered add-on genuinely DOUBLED convexity (0.45 -> 0.97) but breached survivability
  (worst-split maxDD 1.84-1.94x); the give-back stop proved convexity and drawdown are the SAME RAY.
- **Unlevered power response** (2026-07-10, [[runs/atalanta/2026-07-10]]): `conv ** w`
  gross-renormalised - the one form with NO lag and NO leverage. Survivability HELD (worst-split
  maxDD 1.10x the control at w=2), but the convexity gain was not real: NON-MONOTONE (0.4183 control
  -> 0.4660 at w=2 -> 0.4042 BELOW champion at w=4) and Friedman p~=0.59 (cells indistinguishable).
  On 3 names the legs are rarely simultaneously in competing strong trends (w=3 deduped with w=2), so
  a constant-gross power response has almost nothing to redistribute - a near-no-op.

Four theory signals predicted exactly this, all pointing the same way:

1. **Lookback (RA[^3])**: the skew benefit of a convex/sigmoid response is large "particularly for
   shorter lookback windows"; at a LONG lookback like ours "the difference in skew is minimal." We are
   at 189d - exactly where the lever goes quiet.
2. **EV shape (AFML[^5])**: for a MOMENTUM strategy the EV-vs-divergence curve is CONCAVE (edge is in
   the early breakout; crowding / mean-reversion grow later), so the EV-optimal response is w < 1, not
   w > 1. A convex response sizes up precisely as the edge decays - Sharpe-negative.
3. **Drawdown (Concretum[^4])**: pyramiding roughly DOUBLES vol and MDD (48.7%) and cuts Sharpe
   0.96 -> 0.71 - it fights the champion's hard guardrails (worst-split maxDD <= 10.18, calm-split
   floor >= -6%).
4. **Practitioner (Winton[^6])**: the best-in-class UCITS CTA DELIBERATELY constrains scaling-up at
   turning points - "not giving back too much of our P&L at these turning points is a major
   differentiator." The prudent risk-managed book does the OPPOSITE of pyramiding.

Plus the recurring thin-book fact: on 3 correlated macro ETFs the pyramided give-back has no breadth
to diversify - the same re-entry condition that killed speed, barbell, and turngate
([[trend-speed-buys-drawdown-not-convexity]]). Versor[^7] independently confirms long-term trend has
lost its convexity industry-wide; the residual convex payoff lives at the short/non-trend end (the
tail sleeve), not in a re-sized slow harvest.

## Standing conclusion

- The sizing axis is **convexity-shape-optimal already** and now **closed by measurement on all four
  faces**: vol-exponent (`volbeta`, flat), extension pyramiding (levered add-on + give-back stop -
  convexity real but survivability-breaking), tail-parity leg sizing (null), and the unlevered power
  response (convexity gain not real on a thin book). This joins signal, formula, speed, response,
  universe, and build-vs-buy as closed on the atalanta trio.
- The champion's linear, proportional, gross-normalised, inverse-vol response IS the convexity-optimal
  sizing here - by the grid, not by prior. Above the ~0.45 harvest ceiling needs BOUGHT gamma (tail
  sleeve), not a re-shaped harvest.
- **Re-entry condition**: a multi-market book where legs are simultaneously active (so a cross-
  sectional power response has breadth to redistribute) and short-able (so pyramiding's give-back has
  room to diversify) - not the 3-ETF UCITS trio. Same breadth precondition as the whole axis.

## See also

- [[inverse-vol-sizing-is-convexity-neutral-here]] - the vol-exponent end of this axis (also closed)
- [[trend-speed-buys-drawdown-not-convexity]] - the speed axis and the thin-book breadth wall
- [[what-makes-a-trend-sleeve-convex]] - the 0.447 harvest ceiling this pushes on
- [[the-ucits-constrained-tail-sleeve]] - where BOUGHT (super-proportional) convexity belongs

## Sources

[^1]: CFM, "The Convexity of Trend Following", 2018. https://www.cfm.com/wp-content/uploads/2022/12/266-2018-The-Convexity-of-trend-following.pdf
[^2]: Dao, Nguyen, Deremble, Lemperiere, Bouchaud, Potters, "Tail protection for long investors: trend convexity at work", JOIS 2017. https://doi.org/10.21314/jois.2017.093
[^3]: Research Affiliates, "Walking the Tightrope: Trend Following's Tricky Tradeoffs", 2025. https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1077-trend-followings-tricky-tradeoffs-sharpe-ratio-vs-skew.pdf
[^4]: Concretum Group (Zarattini), "Position Sizing in Trend-Following: Volatility Targeting, Volatility Parity, and Pyramiding", 2024. https://concretumgroup.com/position-sizing-in-trend-following-comparing-volatility-targeting-volatility-parity-and-pyramiding/
[^5]: Lopez de Prado, "Advances in Financial Machine Learning" (bet-sizing, sigmoid/power forms); worked implementation e.g. https://www.mql5.com/en/articles/21824
[^6]: The Hedge Fund Journal, "Winton Alma Diversified Macro Fund" (Judes on constraining scale-up at turning points). https://thehedgefundjournal.com/winton-alma-diversified-macro-fund-cta-ucits/
[^7]: Versor Investments, "Has Trend Gone Flat? Return Convexity in Trend Following", 2022. https://www.versorinvest.com/wp-content/uploads/2022/05/Convexity.pdf

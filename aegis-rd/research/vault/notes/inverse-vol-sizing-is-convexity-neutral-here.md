---
title: Inverse-vol sizing is convexity-neutral on the thin trend trio
date: 2026-07-09
tags:
  - note
  - trend
  - convexity
  - sizing
topic: whether the vol-scaling rule leaks convexity, and whether re-sizing can lift it
---

# Inverse-vol sizing is convexity-neutral on the thin trend trio

> [!note] Status
> TESTED (2026-07-09, [[runs/atalanta/2026-07-09#volbeta]]). The sizing axis is closed on the
> atalanta trio: the champion's inverse-vol sizing is convexity-optimal within noise.

> [!abstract] One-line takeaway
> The "inverse-vol de-risks into the payout" convexity leak is real in theory but (a) already
> plugged on our book by the long vol window, and (b) not liftable by re-sizing: sweeping the
> vol exponent leaves convexity flat (Friedman p=0.88). The remaining sizing lever is the tail
> sleeve's equity-linked job, not atalanta's.

## The claim and where it came from

Kaminski-Hoffman ("The Taming of the Skew") show inverse-vol / constant-risk targeting has the
**lowest** skew of the sizing rules, because it cuts a leg's weight exactly as that leg's vol
spikes - i.e. as the crisis leg pays. The apparent implication: our champion sizes each leg by
`score / realized_vol`, so it de-risks the convex legs into their own payout - a structural
convexity leak.

## Why the leak is mostly already plugged

Research Affiliates pin the leak precisely: it bites when a **long trend lookback** is paired with
a **short vol window** (the short window over-reacts to the vol spike). Their fix is a **longer vol
window**. The champion already pins `vol_window = 126` (long) for exactly this reason - the config
comment cites RA: "a long lookback paired with a short vol window negates positive skew ... pinned
so the skew-preserving choice is baked." So the transferable part of the lever was already taken.

## The test: sweep the vol-scaling exponent

`atalanta.keystone_volbeta` generalizes the divisor to `vol ** vol_beta` and sweeps
`vol_beta in {0, 0.25, 0.5, 0.75, 1.0}`; `vol_beta = 1` is full inverse-vol (the champion, nested
control), `vol_beta = 0` is magnitude-only (vol-blind). Champion-anchored: `vol_beta=1` reproduces
held-out `trend_convexity_payoff` 0.4451 bit-for-bit.

| vol_beta | held-out conv | mean maxDD | reversal split (s4) conv / ret |
|---|---|---|---|
| 0.00 | 0.4416 | 7.67 | 0.083 / -1.18% |
| 0.50 | 0.4462 | 7.51 | 0.066 / -1.42% |
| 1.00 (champion) | 0.4451 | 7.28 | 0.024 / -3.05% |

Convexity is **flat** (range ~0.005); **Friedman p ~= 0.88** (cells indistinguishable). `vol_beta=0.5`
nominally leads by +0.001 - noise.

## Why it does not move (two reasons)

1. **Carver's result**: reducing vol-targeting moves *skew* but not the *right tail*, and our metric
   is right-tail-minus-left-tail. Empirically here, lowering the exponent mildly patches the worst
   *reversal* split (holds the crisis legs, s4 -3.05% -> -1.18%) but does not move aggregate
   convexity, and mildly *worsens* mean/worst-split drawdown (more risk in the high-vol legs).
2. **Structural**: on the gross-normalized FORGO book, vol appears in both the leg numerator and the
   gross divisor, so `vol_beta` only re-weights the **cross-sectional** split among three correlated
   macro legs - it is NOT the full **time-series** "let gross rise in stress" ERT mechanism. That
   time-series mechanism (Kaminski's ERT, sizing fund vol to VIX) is **equity-linked** = the tail
   sleeve's job, and would violate atalanta's non-equity substrate rule. Carver also warns it buys
   skew at ~1/3 of Sharpe with no real right-tail gain - "cheaper to buy straddles" (the tail sleeve).

## Standing conclusion

The sizing axis joins signal, response, speed, universe, and build-vs-buy as **closed** on the
atalanta trio. Inverse-vol is convexity-optimal within noise. The residual convexity above the
0.447 harvest ceiling is a **bought-gamma** purchase (tail sleeve), not a re-sizing of the harvest.
Re-entry: the full time-series ERT on a crisis signal - but that belongs to the tail tier, not here.

## See also

- [[trend-speed-buys-drawdown-not-convexity]] - the speed axis (also closed, same day)
- [[what-makes-a-trend-sleeve-convex]] - the harvest ceiling
- [[the-ucits-constrained-tail-sleeve]] - where bought-gamma convexity lives
- [[runs/atalanta/2026-07-09#volbeta]] - the sweep

## Sources

[^1]: Kaminski & Hoffman, "The Taming of the Skew", Campbell & Company, 2016. https://hedgefundalpha.com/strategies/the-taming-of-the-skewness/
[^2]: Rob Carver, "Vol targeting and trend following", qoppac, 2018. https://qoppac.blogspot.com/2018/07/vol-targeting-and-trend-following.html
[^3]: Research Affiliates, "Walking the Tightrope: Trend Following's Tricky Tradeoffs", 2025. https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1077-trend-followings-tricky-tradeoffs-sharpe-ratio-vs-skew.pdf

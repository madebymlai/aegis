---
title: Graveyard
tags:
  - index
  - graveyard
---

# Graveyard

Killed hypotheses. One line each, so dead ideas don't get re-researched. A kill here
means a *clean* test failed - implementation failures (broken grid, bad config) get
fixed and rerun, not buried.

| Hypothesis | Why it died | Killed by |
| ---------- | ----------- | --------- |
| Short legs add crash convexity to a ten-ETF TSMOM sleeve | Even at their best case (slow 252d trend, risk legs only, 5-10% entry band, modest 0.5%/yr borrow) every short-bearing candidate ranked below the long-only book, and the short overlay lost in 2022 itself (-0.55 held-out Sharpe vs +0.09 long-only); thin correlated book + whipsaw + carry never pay | [[runs/aegis/2026-06-10#20260610T183709952487Z_etf_aegis_v3_dual\|2026-06-10 v3]] |
| A wider entry band on the haven leg of the crisis blend cuts the 2023 chop bleed | The optimizer never selected the gate (best candidate chose band 0.0) and gated candidates still bled in 2023; the drag is trend-reversal whipsaw, not weakly-trending holdings | [[runs/aegis/2026-06-10#20260610T184512806692Z_etf_aegis_v5_blend_gated\|2026-06-10 v5]] |
| A two-speed barbell (fast+slow blended TSMOM) cuts the 2023 chop bleed in the crisis blend | The fast leg added whipsaw instead of dampening turning points in this thin ten-ETF book: 2023 worsened (-0.99 vs v4's -0.50) and overall held-out Sharpe dropped (+0.731 vs +1.008); the broad-futures speed-diversification result did not transfer | [[runs/aegis/2026-06-10#20260610T190447082142Z_etf_aegis_v6_barbell\|2026-06-10 v6]] |
| A fast-vol gross throttle (Yang-Zhang or close-to-close on SPY, vol-target scaling to cash) cuts the held-out 2018 fast-crash loss | Coincident detection arrives post-shock: best 2018 improvement +0.01 (YZ) / +0.12 (CC) vs the +0.5 gate; the Feb-2018 scale cut lands 4-5 days after the bottom and de-risks into the V-recovery, and Q4 stays unthrottled through mid-October; the throttle's only effect is mild vol-targeting in years the sleeve already handles | [[runs/aegis/2026-06-10#20260610T205352247752Z_etf_aegis_v11_yzthrottle\|2026-06-10 v11]] |
| Yang-Zhang range vol beats close-to-close as the fast-crash throttle driver (the in-bar speed gain) | At matched windows the *slower* close-to-close estimator won on every count (2018 -1.43 vs -1.54, composite 0.211 vs 0.161); with a post-shock trigger, per-bar efficiency only adds reaction to noise | [[runs/aegis/2026-06-10#20260610T205502094969Z_etf_aegis_v12_ccthrottle\|2026-06-10 v12]] |

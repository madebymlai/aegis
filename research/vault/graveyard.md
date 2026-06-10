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

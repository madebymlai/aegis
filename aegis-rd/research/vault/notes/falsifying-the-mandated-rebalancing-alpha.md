---
title: Falsifying the mandated-rebalancing alpha
date: 2026-07-17
tags:
  - note
  - flow-alpha
  - falsification
  - strategy-search
topic: whether the Harvey-Mazzoleni-Melone rebalancing front-run still pays after publication, costs and timing, and whether it improves Atalanta
related:
  - "[[front-running-mandated-rebalancing-flows]]"
  - "[[the-tiered-strategy-roster]]"
  - "[[accessible-ordinary-market-income-after-an-open-search]]"
  - "[[what-is-a-strategy]]"
---

# Falsifying the mandated-rebalancing alpha

> [!note] Status
> TESTED (2026-07-17, throwaway falsification prototype at `aegis-rd/tmp/prototype_mandated_rebalancing/`,
> run with `uv run python tmp/prototype_mandated_rebalancing/report.py`). Verdict: **DEAD/REJECT -
> alpha likely decayed; do not proceed.** No paper-trading phase, no allocation.

> [!abstract] One-line takeaway
> The paper's mechanism reproduces cleanly on 2000-2023 futures data (threshold signal -13.1 bp/sd,
> NW t = -3.99; frozen strategy Sharpe 1.16 gross) - and then dies exactly where the decay
> literature said it would: 2024-latest Sharpe 0.19 (t = -0.65), post-publication (2025+) Sharpe
> -0.24 (t = -0.44). The response keeps its sign but is statistically and economically nil after
> the paper circulated. The pairing test independently fails: mixed 60/40 with Atalanta the
> candidate LOWERS whole-book MPPM CE by -0.020 and contributes -0.33%/month in Atalanta's
> worst-decile months. Two failed gates, either sufficient.

## What was tested

The falsification ladder from the [[front-running-mandated-rebalancing-flows|research note]],
run bottom-up and designed to prove the alpha dead: (1) reproduction correctness, (2) recency
and decay, (3) implementable economics, (4) Atalanta pairing, (5) prospective decision. The
construction is the paper's, pinned from the Daniel discussion slides and the two practitioner
replications: threshold signal = mean 60/40 drift across reset bands 0-2.5% in 0.1% steps;
calendar signal = drift since month-end reset, traded in the last 5 sessions with the last-day
reversal capture; combined = linear average, inverted, on the S&P-vs-10y-Treasury futures
spread; weight known at close t earns the t to t+1 spread return (look-ahead guarded).

Data: Yahoo continuous ES/ZN futures 2000-09..2026-07 (unadjusted splices, ~4 roll joints/yr),
validated against IBKR CONTFUT on the overlap era (ES corr 0.980, ZN corr 0.994); 1997-09..
2000-09 exists only as a labeled index/yield proxy extension. Actual QSPX (2025-06+) and MTN
(2024-03+) quotes from IBKR. Atalanta = the locked `trend_floor` stream reproduced through the
production path (`scripts/floor_evaluation.py`), 2018-01..2026-06.

## The ladder, stage by stage

**1. Reproduction: PASS.** Threshold signal predicts the next-day stock-bond spread at -13.1
bp per sd, Newey-West t = -3.99 (paper: ~ -17 bp equity leg, t ~ 4); calendar signal -36.2
bp/sd on pressure days (t = -3.90). Frozen combined rule 2000-09..2023-03: Sharpe 1.16 gross,
CAGR 11.5%, skew +6.6, maxDD -12.5% - inside the replication range (Quantitativo 0.94,
QuantReturns 1.24). The long-only loser-rule control also matches its practitioner report
(0.93 gross vs ~0.78 reported). Not tuned to agree: the signal constants (0.012 normalization,
5-session window) are the replication's, fixed ex ante.

**2. Recency: FAIL - the kill.** Same frozen rule, windowed: pre-2020 Sharpe 1.16 (t = -3.55);
2020-2023 Sharpe 1.13 (t = -2.69); **2024-latest Sharpe 0.19, beta -5.3 bp/sd, t = -0.65;
post-publication (2025-01+) Sharpe -0.24, beta -5.0 bp/sd, t = -0.44.** The coefficient
retains its sign but loses ~80% of its magnitude and all significance. Notably our public-data
run does NOT reproduce the L&G null on their own window (2020-01..2025-06 shows t = -2.50,
Sharpe 0.95) - the decay is concentrated in 2024+, i.e. after the paper's circulation, which
is the McLean-Pontiff post-publication signature the research note pre-registered as the
failure clause, not the CTA-offset story L&G tell.

**3. Implementable economics: passes on the old sample, with two red flags.** Futures costs
are not the problem: 0.73%/yr drag on ~97x/yr turnover, net Sharpe 0.79 on 2020+. But (a)
**one session of execution delay destroys the whole edge** (full-sample Sharpe 1.00 to 0.15,
maxDD -13% to -42%) - the effect lives at the US close, so European-hours execution forfeits
it, answering the research note's open question 5 in the worst direction; (b) the integer
QSPX-MTN sleeve on $11k runs 1.8-3.5%/yr in costs, and over its actual 13 months of IBKR
history returned Sharpe -0.65 (too short for significance; consistent with stage 2). MTN
tracks the Ultra 10y (corr 0.994 to TN), which carries ~1.4-1.5x the vol of the paper's
conventional ZN per notional - the approximation is not the paper's trade.

**4. Atalanta pairing: FAIL.** Aligned monthly against the production Atalanta stream
(102 months, 2018-01..2026-06), using the established floor-pair measure: correlation +0.095
(passes the H1 gate), and the candidate was spectacular in the windows Atalanta historically
misses (+38.2% in the 2020 V-reversal vs +9.4%; +5.4% in the 2018 fast gap vs 0.0%) - but its
mean in Atalanta's worst-decile months is **-0.33%**, the 60/40 mix lowers MPPM CE by -0.0199
and Sharpe by -0.238, and every block-bootstrap CI straddles zero. The recent dead era poisons
the aligned sample; low correlation was never the bar, positive marginal utility was.

**5. Decision: DEAD/REJECT.** First failing gate is stage 2; stage 4 fails independently.

## Caveats that do NOT rescue it

- The 1997-2000 proxy extension and splice noise affect level estimates, not the 2024+ death:
  the recent windows are pure futures data cross-validated against IBKR.
- The post-publication window is short (386 obs) - but "too short to prove alive" is not a
  reason to fund a flow trade whose measured response is nil; the pre-registered decay clause
  reads significance loss as the kill.
- Daily bars cannot separate the 16:00 cash close from the 17:00 futures settle; a
  finer-grained timing story could only shrink the residual further, not revive it.

## What survives

- The **decay monitor worked as designed**: the rolling signal-response regression (H3 of the
  research note) is exactly what detected the death before any capital was staged. That
  component pattern is portable to any future flow-alpha candidate.
- The reproduction machinery (pure signal construction, NW predictive regression, verdict
  gates) lives in the prototype's `engine.py` and lifts cleanly if the family is ever
  revisited.
- Re-entry condition (graveyard): the prospective rolling 36-month regression of next-day
  stock-bond spread on the threshold signal regains significance (t <= -2) on fresh
  post-2026 data, or a structural payer change reverses (e.g. overlay/randomized rebalancing
  adoption measurably recedes). Re-running the same backtest on the same sample is not a
  resurrection.

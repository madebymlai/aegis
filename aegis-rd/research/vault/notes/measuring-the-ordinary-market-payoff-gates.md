---
title: Measuring the ordinary-market payoff gates
date: 2026-07-17
tags:
  - note
  - convergent
  - measurement
  - falsification
topic: the two pre-registered gate measurements that decide whether the convergent ordinary-market seat can be built from the liquid macro UCITS set - commodity-index weekly reversion and dealer-gamma-conditioned equity reversion
related:
  - "[[a-behavioural-atlas-of-ordinary-markets]]"
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[verifying-strategy-family-membership]]"
  - "[[falsifying-the-mandated-rebalancing-alpha]]"
---

# Measuring the ordinary-market payoff gates

> [!note] Status
> MEASURED (2026-07-17, throwaway measurement prototype at `aegis-rd/tmp/prototype_ordinary_market_gates/`,
> run with `uv run python tmp/prototype_ordinary_market_gates/gate1_commodity_vr.py` and
> `.../gate2_gamma_autocorr.py`; pre-registration in the prototype README, written before results).
> Verdict: **both gates KILL.** No strategy design proceeds from atlas facts 3 or 4.

> [!abstract] One-line takeaway
> The two payoff-shaped behavioural facts the atlas ranked as candidate material for the convergent
> seat both fail their pre-registered gates on our substrate: the broad-commodity line shows no
> weekly reversion at all (ICOM weekly VR(2) = 1.012, joint wild-bootstrap p = 0.43, and the ^BCOM
> cross-check's monthly dependence is significantly *positive* - trend-family structure), and the
> dealer-gamma conditioning goes the *wrong way* at daily-or-slower cadence (top-gamma
> autocorrelation is less negative than bottom-gamma, delta_b = +0.15, p = 0.97). What survives is
> exactly what the atlas predicted for the kill branch: the second moment. GEX terciles condition
> realized volatility monotonically (mean |daily move| 108 -> 66 -> 46 bp), so the gamma state stays
> as break-condition instrumentation. The ordinary-market convergent lane from the liquid macro
> quartet is now closed; the seat's remaining path is the event/single-stock lane.

## What was measured

The two gate measurements from [[a-behavioural-atlas-of-ordinary-markets]] (hypothesis list;
facts 3 and 4), executed as pure measurements - no strategy, no P&L objective, no parameter
search beyond the pre-registered spec. Criteria were written in the handoff and the prototype
README before any result was seen. Both use wild-bootstrap inference (Rademacher weights,
B = 4,999, seed 42), per the atlas toolbox's warning against the asymptotic z.

**Gate 1 - weekly serial dependence of the broad-commodity index line.** Claim (atlas fact 3,
Da-Tang-Tao 2018): post-financialization, broad commodity indices show significantly negative
daily autocorrelation from index-flow shock propagation; only a weekly/monthly version could
clear the cost wall. Measurement: Lo-MacKinlay VR with heteroskedasticity-robust M2 and
Chow-Denning joint statistic, weekly k in {2,4,8,13} and monthly k in {2,3,6,12}, on the ICOM
line (catalog LAST closes, 2017-12..2024-12, all post-2006 by construction) and the ^BCOM index
(Yahoo, 1991-07..2026-07) as cross-check. PROMOTE required weekly joint p < 0.05 with VR(2) < 1
plus sign stability across two non-overlapping sub-windows.

**Gate 2 - dealer-gamma-conditioned reversion on the equity line.** Claim (atlas fact 4,
Barbon-Buraschi): positive dealer-gamma regimes dampen index moves; unknowns were (a) a
daily-or-slower footprint and (b) existence in European-hours prints. Measurement: lag-1
autocorrelation slope of SPX close-to-close returns by tercile of the rolling 252d percentile of
SqueezeMetrics GEX (2011-05..2026-07), delta_b = b_top - b_bottom tested one-sided by wild
bootstrap under a common-slope null; the same regression on CSPX's own LSE prints (2018-01..
2024-12, regime lagged one day so it is fully causal for the European return window). PROMOTE
required (a) delta_b < 0 significant with stable sub-window sign AND (b) survival in the CSPX
prints.

## Gate 1 result: KILL

| Sample | VR(2) | joint p |
| --- | --- | --- |
| ICOM weekly, full (the gate) | 1.012 | 0.433 |
| ICOM weekly, 2018-01..2021-06 | 1.089 | 0.077 |
| ICOM weekly, 2021-07..2024-12 | 0.968 | 0.953 |
| ICOM monthly, full | 1.184 | 0.144 |
| ^BCOM weekly, post-2006 | 1.014 | 0.095 |
| ^BCOM monthly, post-2006 | 1.119 | **0.023** |
| ^BCOM daily, post-2006 | 0.997 | 0.897 |
| ^BCOM daily, pre-2006 | 1.005 | 0.985 |

Three findings, each independently fatal:

1. **No weekly reversion exists on the line.** ICOM weekly VR is indistinguishable from 1 and
   its point estimate sits on the wrong side (above 1); the sub-window signs flip. The
   pre-registered KILL condition ("weekly VR indistinguishable from 1") is met exactly.
2. **The significant dependence that does exist is positive, at monthly horizon** (^BCOM
   post-2006 monthly joint p = 0.023, VR rising to 1.55 at 6 months). That is time-series
   momentum - the divergent family's own structure - so per
   [[verifying-strategy-family-membership]] it is not candidate material for this seat under
   any construction.
3. **The upstream daily claim itself does not reproduce.** On 2006-2026 ^BCOM closes the daily
   VR(2) is 0.997 (p = 0.85), statistically identical to the pre-2006 contrast (1.005). The
   atlas flagged fact 3 as resting on one working paper at daily frequency only; on the current
   sample the single-source fact is contradicted outright, not merely eroded by aggregation.

Effect size against the wall: implied weekly edge ~2 bp/event (ICOM and ^BCOM alike) against
the 15-75 bp round trip. Two orders of magnitude short even before significance.

## Gate 2 result: KILL

| Regression | delta_b (top - bottom) | one-sided p |
| --- | --- | --- |
| SPX daily, full 2012-05..2026-07 | +0.152 | 0.970 |
| SPX daily, sub-window 1 | -0.054 | 0.239 |
| SPX daily, sub-window 2 | +0.240 | 0.985 |
| SPX weekly (week-mean regime) | -0.023 | 0.437 |
| CSPX daily (European prints) | -0.045 | 0.295 |
| Robustness: GEX/SPX^2 regime | +0.102 | 0.911 |

The first moment goes the wrong way: daily autocorrelation in the *top*-gamma tercile is mildly
positive (b = -0.01 to +0.02 across windows) while the strong mean reversion lives in the
*bottom*-gamma (stressed) tercile (b = -0.16, full sample; -0.24 in the 2019-2026 half). The
dampening claim as a payoff - "fade moves harder when dealers are long gamma" - is refuted at
daily-or-slower cadence; the reversion that exists at this cadence belongs to stressed states,
which are the defence sleeve's territory, not the convergent seat's. Weekly and European-hours
expressions are null (p = 0.44 / 0.30). Implied fade edge in the top tercile: 0.3-3 bp/event
daily against the 15-75 bp wall.

What survives is the regime description, strongly: mean |daily SPX move| falls monotonically
108 -> 66 -> 46 bp from bottom to top GEX tercile (sd 156 -> 90 -> 66 bp), and the same
monotone pattern appears in the CSPX prints (112 -> 76 -> 52 bp). This is the pre-registered
kill branch's own prediction - the gamma state is real, publicly observable, and conditions the
second moment at daily cadence, so it stays as **break-condition instrumentation** (the
gamma-flip exit trigger of atlas fact 4 and a candidate transition variable for the
break-condition bake-off hypothesis), not as a payoff.

## Consequences for the seat

The atlas ranked exactly two of its five facts as payoff-shaped for the convergent seat: fact 3
(commodity index reversion) and fact 4 (gamma-dampened ranges). Both are now dead as payoffs on
our substrate, killed by pre-registered gates, and the deaths are of different kinds - fact 3's
underlying anomaly appears to have never existed at reachable cadence (and its daily version
fails to reproduce), while fact 4's mechanism is real but leaves no first-moment footprint at
the cadences the cost wall allows.

The remaining atlas checkboxes are conditioning and instrumentation measurements (time-in-range
fractions, bond-channel re-tests, gold state-switch, break-condition bake-off, substrate gaps),
worth doing for the book's risk architecture but incapable of filling the seat. The convergent
ordinary-market lane from the liquid macro quartet is therefore closed. The seat's search
continues exclusively on the event/single-stock lane of [[finding-a-buildable-convergent-engine]]
(cash-merger convergence, already dispatched as its own research round).

## Measurement notes

- The first Gate 1 run produced VR(k) = 1/k on every sample - the signature of dividing by k
  twice (the Lo-MacKinlay m divisor already contains k). The bug was caught before any
  interpretation because the wild-bootstrap p-values were insensitive to enormous nominal z
  values; the fixed estimator was size-checked on simulated white noise (200 sims at n = 400:
  4.0% rejection at nominal 5%, mean VR(2) = 1.007) and recovers MA(1) and AR(1) dependence
  with the correct signs.
- Known caveats accepted in the pre-registration: ICOM weekly n = 366 gives low power (which
  biases a significance gate toward KILL - the conservative direction for promotion); the
  public GEX series spans a methodology change and is treated as one series; ICOM/CSPX are
  accumulating lines so no distribution adjustments are involved, and the SPX leg comes from
  the same SqueezeMetrics file as GEX, so the (a) regression has no alignment risk.
- Data: ICOM/CSPX daily LAST closes from the warm catalog (no IBKR connection); ^BCOM from the
  Yahoo chart API; GEX/DIX from the public SqueezeMetrics CSV (2011-05-02..2026-07-16, fetched
  2026-07-17, cached beside the prototype).

# PROTOTYPE — ordinary-market gate measurements (throwaway)

Throwaway measurement code answering two pre-registered gate questions from
[[a-behavioural-atlas-of-ordinary-markets]] (hypothesis checkboxes 2 and 6).
Pure measurements: no strategy, no P&L objective, no parameter search beyond
the spec below. Handoff: `/tmp/handoff-prototype-ordinary-market-gates.md`.

Run (from `aegis-rd/`):

```
uv run python tmp/prototype_ordinary_market_gates/gate1_commodity_vr.py
uv run python tmp/prototype_ordinary_market_gates/gate2_gamma_autocorr.py
```

Warm catalog reads only (no IBKR); ^BCOM and SqueezeMetrics CSV are fetched
over HTTP and cached in `.cache/` beside this file.

---

## Pre-registration (written 2026-07-17, before any measurement ran)

Shared: log returns; significance level 5%; wild bootstrap with Rademacher
weights, B = 4,999, seed 42. Weekly series = last close per W-FRI week;
monthly = last close per calendar month. Effect sizes reported in bp/event
against the 15–75 bp round-trip cost wall (atlas cost table, ~€10k orders).

### Gate 1 — weekly serial dependence of the broad-commodity index line

Claim under test (atlas fact 3): post-financialization, broad-commodity
*indices* show significantly negative daily autocorrelation. Only the
weekly/monthly version is reachable over the cost wall.

- **Series**: ICOM.LSEETF daily LAST close (catalog, 2017-12-29..2024-12-31,
  full available line history — entirely post-2006 by construction);
  cross-check ^BCOM index close (Yahoo, 1991-07..2026-07), full sample,
  post-2006 sub-sample, and pre-2006 sample as the financialization contrast.
- **Statistic**: Lo–MacKinlay VR(k) on overlapping k-period sums with the
  heteroskedasticity-robust M2 z-statistic; Chow–Denning joint statistic
  MV = max_k |M2(k)|; inference by wild bootstrap (never the asymptotic z —
  atlas toolbox). Per-horizon bootstrap p-values reported alongside.
- **Horizons**: weekly k ∈ {2,4,8,13}; monthly k ∈ {2,3,6,12}; daily
  k ∈ {2,5,10,20} reported as context only (the claim's native frequency —
  not a gate criterion, it is below the cost wall).
- **Sub-windows (sign stability)**: ICOM weekly, 2018-01-01..2021-06-30 vs
  2021-07-01..2024-12-31; stability = sign(VR(2) − 1) equal in both.
  ^BCOM post-2006 halves 2006-01..2016-06 vs 2016-07..2026-07 reported as
  cross-check.
- **Effect size**: implied bp/event = |VR(2)−1| × mean|weekly return| × 10⁴
  (VR(2)−1 ≈ ρ₁; the expected one-event edge of fading last week's move).
- **PROMOTE** if ICOM weekly joint-test p < 0.05 with VR(2) < 1 AND
  sign(VR(2)−1) < 0 in both ICOM sub-windows.
- **KILL** if weekly VR is indistinguishable from 1 (joint p ≥ 0.05) — the
  daily effect does not survive aggregation. Record in the article checkbox
  and graveyard.

### Gate 2 — dealer-gamma-conditioned daily/weekly behaviour, equity line

Claim under test (atlas fact 4): positive dealer-gamma regimes dampen
equity-index moves; unknowns: (a) a footprint at daily-or-slower cadence,
(b) existence in the European-listed line's own prints.

- **Gamma regime**: SqueezeMetrics GEX (public CSV). Raw GEX trends with
  market cap, so the primary regime variable is the rolling 252-trading-day
  percentile rank of GEX (min 126 obs warmup); terciles at 1/3 and 2/3.
  Robustness (reported, not a gate): full-sample terciles of GEX/SPX².
- **(a) US close-to-close**: SPX close from the same CSV (exactly aligned
  with GEX). Daily: r_{t+1} = Σ_g I_g(t)(a_g + b_g r_t) with g = tercile of
  GEX_t; test Δb = b_top − b_bottom < 0, one-sided wild-bootstrap p
  (restricted common-slope model under the null). Weekly: W-FRI returns,
  regime = mean GEX percentile within week w, same regression for
  r_{w+1} on r_w. Sub-windows: sample halves (2012-05..2019-06 /
  2019-07..2026-07); stability = Δb < 0 in both.
- **(b) European prints**: CSPX.LSEETF daily LAST close (catalog,
  2018-01..2024-12). Regime = tercile of GEX_{t−1} (last GEX published
  *before* the CSPX t→t+1 return window opens — fully causal; for SPX,
  GEX_t already precedes the r_{t+1} window). Same regression and Δb test on
  the full CSPX window; sub-window signs (2018-01..2021-06 /
  2021-07..2024-12) reported.
- **Descriptive (no gate)**: mean |r| and stdev by tercile — the
  Barbon–Buraschi dampening footprint (~20 bp abs-move reduction is the
  reference point).
- **Effect size**: bp/event = |b_top| × mean|r_t| × 10⁴ (expected one-event
  edge of fading the prior move in the top-gamma regime), daily and weekly.
- **PROMOTE** if (a) Δb < 0 with p < 0.05 daily or weekly AND sign stable
  across both sub-windows AND (b) Δb < 0 with p < 0.05 in CSPX's own prints.
- **KILL** if the effect exists only intraday or only in US close-to-close
  data — then it is break-condition instrumentation only, not a payoff
  candidate.

### Known data caveats (accepted before running)

- ICOM and CSPX are accumulating UCITS lines (no distribution gaps); SPX is
  an index; the GEX file's price column is the SPX close. No dividend
  adjustment issues for return autocorrelation at these cadences.
- ICOM weekly n ≈ 365, monthly n ≈ 84: low power is acknowledged; the gate
  is significance-based, so low power biases toward KILL, which is the
  conservative direction for a promotion gate.
- GEX methodology changed over the years (GEX → GEX+ era); the published
  CSV is treated as one series — a real-world constraint of the public
  proxy, noted in the writeup.

---

## RESULTS (2026-07-17) — both gates KILL

**Gate 1: KILL.** ICOM weekly VR(2)=1.012, joint p=0.4328 (indistinguishable
from 1, wrong side of it); sub-window VR(2) signs flip (1.089 / 0.968).
^BCOM cross-check: weekly VR(2)=1.014 post-2006 (joint p=0.095), and monthly
post-2006 dependence is significantly *positive* (VR(3)=1.26, VR(6)=1.55,
joint p=0.023) — trend-family structure, not reversion. The claimed daily
negative autocorrelation does not reproduce on 2006–2026 ^BCOM closes
(VR(2)=0.997). Implied weekly edge ~2 bp/event vs the 15–75 bp wall.

**Gate 2: KILL.** Daily Δb(top−bottom) = +0.152, one-sided p=0.970 — the
top-gamma tercile's autocorrelation is *less* negative than the bottom's
(the strong reversion lives in the stressed bottom tercile, b=−0.16); weekly
Δb=−0.02 p=0.44; CSPX European prints Δb=−0.045 p=0.30; sub-window signs
flip. Implied fade edge 0.3–3 bp/event daily. What survives: the
second-moment dampening footprint is real and monotone (mean |daily r|
108→66→46 bp from bottom to top GEX tercile) — break-condition
instrumentation, exactly the KILL branch's prediction.

**Methods incident**: the first Gate 1 run showed VR(k) ≈ 1/k on every
sample — the Lo–MacKinlay `m` divisor already contains `k`, and the code
divided by `k` again. Caught via the bootstrap p-values' insensitivity,
fixed, and the fixed estimator size-checked on simulated white noise
(200 sims, n=400: 4.0% rejection at nominal 5%, mean VR(2)=1.007).

Durable record: `research/vault/notes/measuring-the-ordinary-market-payoff-gates.md`.

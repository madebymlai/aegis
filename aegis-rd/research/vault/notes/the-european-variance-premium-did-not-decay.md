---
title: The European Variance Premium Did Not Decay
date: 2026-07-27
topic: variance-risk-premium
status: measurement
related:
  - "[[the-payer-did-not-leave-the-supply-arrived]]"
  - "[[carry-as-the-short-gamma-income-pole]]"
  - "[[the-skew-is-the-product]]"
  - "[[what-makes-a-convergent-sleeve-an-income-engine]]"
tags:
  - note
  - variance-risk-premium
  - demeter
  - measurement
---

# The European Variance Premium Did Not Decay

> [!abstract] Measurement
> VSTOXX minus the volatility that actually followed on EURO STOXX 50 runs **+3.34 vol points
> post-2012** (t ~ +6.4, positive on 78.0% of days, n = 3,516), and it is flat across every
> two-year window from 2013 to today. The most recent cell, 2025-2026, reads +3.61 against a
> full-sample +3.37. There is no decay in the European raw gap. The payoff shape is the one
> the convergent seat is hired for: **+7.60 vol points in the calm decile, -5.20 in the
> crisis decile**, with the five worst observations all falling in the week before the
> February 2020 crash.

## What was measured

`VRP_t = VSTOXX_t - RV_{t -> t+21}`, where `RV` is the annualized realized volatility of
EURO STOXX 50 over the **following** 21 trading days. Both legs are daily closes for
`^V2TX.XEUR` and `^SX5E.XEUR` (IBKR conIds 35913933 and 4356500), read through the ordinary
catalog path - `seed_instrument_definitions` -> `catalog_data_port` -> `load_window` ->
`read_native_bars` - so the series is catalog-resident and a later config can reference it.
Sample 2011-01-03 to 2026-06-30, 3,902 overlapping observations.

| window | mean (vol pts) | t | share > 0 |
| --- | ---: | ---: | ---: |
| full sample | +3.37 | +6.77 | 77.8% |
| post 2012-08 | **+3.34** | +6.35 | 78.0% |
| 2013-2014 | +1.93 | +1.93 | 66.0% |
| 2015-2016 | +3.05 | +2.11 | 72.9% |
| 2017-2018 | +3.67 | +4.88 | 87.0% |
| 2019-2020 | +1.98 | +0.85 | 71.9% |
| 2021-2022 | +5.18 | +3.87 | 82.3% |
| 2023-2024 | +3.66 | +4.25 | 80.9% |
| 2025-2026 | +3.61 | +2.37 | 82.4% |

An independent first pass through raw `ibapi`, on a shorter window IBKR served directly
(2011-08-08, 3,777 observations), agrees throughout: full +3.40, post-2012 +3.32, calm decile
+7.68, crisis decile -4.87, and every two-year cell within 0.1 vol points. The two paths are
reported because agreement between them is what rules out a pipeline artifact.

The series is verified real rather than a vendor artifact: VSTOXX peaks at **85.6 on
2020-03-16**, reaches 53.5 in the 2011 euro crisis, and has a median of 19.1.

## The shape is the product

Conditioning on the volatility that followed:

- forward RV in the **bottom decile**: mean VRP **+7.60**
- forward RV in the **top decile**: mean VRP **-5.20**

The five worst observations are 19, 20, 21, 24 and 26 February 2020 - selling implied at
12.9 to 24.5 into realized volatility of 63 to 77, for losses near 50 vol points each. The
2019-2020 cell keeps a positive mean (+1.97) but its standard deviation triples to 11.53 and
its t collapses to +0.84.

That is the accrue-in-calm, give-back-in-dislocation profile
[[what-makes-a-convergent-sleeve-an-income-engine]] specifies, measured directly on the
premium rather than inferred from a strategy's equity curve. It is also why
[[the-skew-is-the-product]] applies: the concavity is the good being sold, not a defect.

## Four things this does not establish

1. **It does not test the 2012 structural break.** IBKR's history starts 2011-07, so the
   pre-break window holds 252 observations of the euro crisis. The +4.56 pre-break figure is
   noise. This neither replicates nor refutes Dew-Becker and Giglio.
2. **It measures the raw gap, not the risk-adjusted alpha.** Those are different objects, and
   the alpha is the one Dew-Becker and Giglio test - see
   [[the-payer-did-not-leave-the-supply-arrived]], which is the governing correction here. A
   near-zero alpha stays fully consistent with every number above. For a pole hired to bear
   crash risk rather than to generate alpha, the gap is the relevant object, but the two must
   not be blurred.
3. **The marks are TRADES, not QUOTE.** A `:QUOTE` mark was requested first; IBKR serves no
   BID/ASK for either index, which is correct for a calculated level rather than a two-sided
   instrument. The fallback fired and is named rather than assumed.
4. **Vol points are not a return.** +3.3 vol points is the gross premium on offer before any
   cost of harvesting it. It establishes that the payer exists, not that this book can bank it.

Overlapping 21-day windows mean the reported t values use an effective sample size of
`n / 21` rather than a Newey-West correction. Read them as directional.

## Why this matters more than a new hypothesis

`demeter.vol_carry` was already promoted to **champion concave pole** on
[[runs/demeter/2026-06-13|2026-06-13]], on a decisive pass across all six parameter cells:
quarterly skew -1.18, crash-conditional -0.95%, Sharpe +0.57, versus distribution carry's
-0.13 and -0.16% at matched volatility. Roughly nine times the skew and six times the crisis
loss.

Its recorded next step was *"needs tz handling for the ^VIX index feeds vs the VXX ETF in the
data layer."* That work never happened. The config moved to `configs/demeter/archive/` and
distribution carry became the pole by default.

The blocker is **not** the data layer, and an intermediate reading of this note said it was.
IB simplified symbology (ADR-0005) already decodes indices: `_decode_index_contract` sits
third in its chain, triggered by a **caret-prefixed symbol**, building
`IBContract(secType="IND", localSymbol=symbol[1:])`. The documented forms are `^SPX.CBOE`
and `^NDX.NASDAQ`.[^ibsym] Verified against the live gateway with unmodified `aegis-data`:
`^V2TX.XEUR` and `^SX5E.XEUR` both qualify and return `IndexInstrument` definitions, and the
provider resolves the `DTB` / `EUREX` exchange ambiguity itself.

The earlier failure - `V2TX.EUREX` answering *"Cannot parse, use 1-digit year for FUT and
FOP"* - was the **missing caret**, not missing index support. Note that
[[runs/demeter/2026-06-13|the 2026-06-13 diary]] already wrote the feeds as `^VIX` and
`^VIX3M`, in the correct form.

So the recorded blocker stands as written and is small: timezone and calendar alignment
between an index feed (MET for VSTOXX, US/Central for VIX) and the ETF leg it must merge
with. That is a real chore and it is the whole chore. `aegis-rd-p4zd` was filed against the
wrong diagnosis and is closed as not-a-bug.

The consequence is unchanged and now cheaper: the seat's measured champion was set aside for
a plumbing reason, and the payer it was built on is still there at +3.3 vol points with no
visible decay.

## Sources

- Measurement scripts and the extracted series: session scratchpad, `eu_vrp.py` and
  `eu_vrp.csv`, run 2026-07-26 against the live paper gateway on port 4002.

[^ibsym]: NautilusTrader, [Interactive Brokers integration - Symbology](https://nautilustrader.io/docs/latest/integrations/ib) - the simplified-symbology examples list `^SPX.CBOE` and `^NDX.NASDAQ` as the index forms alongside `SPY.ARCA`, `ESM4.CME` and `EUR/USD.IDEALPRO`. Official adapter documentation.
- [[the-payer-did-not-leave-the-supply-arrived]] - the governing correction on what the
  Dew-Becker and Giglio result does and does not claim, and the supply-side mechanism with
  the right sign. Its European instance, retail structured-product issuance compressing
  EURO STOXX 50 implied volatility around 60-70% moneyness, is the reason a European
  measurement could not be assumed to inherit the American one.

# PROTOTYPE — cross-market variance risk premium around August 2012

> **Read this before the numbers below.** This prototype measures a **raw implied-minus-
> realized volatility gap**, not a risk-adjusted alpha. Dew-Becker & Giglio (Chicago Fed
> WP 2025-17, "DBG") find the US index-option variance risk premium's **CAPM alpha**
> collapsed to zero at a structural break dated August 2012. A raw gap that stays
> positive is equally consistent with "a genuine premium survived" and with "this was
> always pure compensation for market beta, never risk-adjusted out" — DBG's finding is
> specifically about the *alpha*, and no free data source found anywhere in this
> prototype or its sibling (`eu_variance_premium`) lets that be computed for any market.
> **This prototype cannot confirm or refute DBG on their own terms.** What it can do is
> answer a narrower question: does the US raw gap behave differently around 2012-08 from
> other markets' raw gaps? Either answer is informative on its own terms — see "Verdict."

## Question

Nobody has split a multi-market implied/realized-volatility panel at the August-2012
break DBG date for the US. Qiao, Xu, Zhang & Zhou (JBF 2024) report a raw gap (not a
CAPM alpha) that is positive in 19 of 20 markets over 2006-2023, but ran no structural
break test at all, and their full-sample US average straddles both sides of a 2012
break — consistent with either "the US alone flattened" or "everyone flattened
together." This prototype builds, per market, an implied-vol index series, a realized-
vol series from that market's own equity index closes, their raw gap, and a pre/post-
2012-08 comparison — then asks the cross-sectional question: **is the change in the US
distinguishable from the change elsewhere?**

## Reuse, not a second implementation

This shares its statistical core with the sibling `eu_variance_premium` prototype rather
than reimplementing it:

- `forward_realized_variance`, `variance_gap`, `newey_west_mean_test`, and
  `structural_break_test` are imported directly from `eu_variance_premium.model` —
  unchanged, and already generic (nothing in their implementation is VSTOXX-specific
  despite the parameter names).
- `eu_variance_premium.yahoo_history` was **generalized, not duplicated**: it used to
  hardcode EURO STOXX 50; it now exposes ticker-generic `load_close_series` /
  `load_log_returns`, with `load_sx5e_log_returns` kept as a one-line wrapper so that
  prototype's own README, tests, and `__main__.py` are unchanged (verified: its 18
  existing tests still pass unmodified). This module reuses that generalized loader for
  every other market's tickers instead of a second hand-rolled Yahoo Finance client.
- Europe's VSTOXX series is loaded from `eu_variance_premium.stoxx_history` and its
  checked-in, sha256-verified fixture — untouched. Re-running Europe here reproduces
  that prototype's own numbers exactly (see "Real result" below), which is a consistency
  check on the reuse, not a new measurement.
- The only genuinely new statistic is `cross_market.compare_break_changes` — a
  cross-sectional z-test comparing two markets' post-minus-pre changes. It composes on
  top of `StructuralBreakResult` rather than adding a second break-test implementation.

## Coverage: what free data actually has

The brief asked to check, not assume, which volatility indices are retrievable via
`yfinance`. Every ticker below was fetched, not guessed from memory — reproduce with
`.venv/bin/python -m _prototyping.global_variance_premium` (the default, no-argument
mode; see `--probe` below). 26 candidate tickers across 13 additional markets were
tried and failed; that failure list is kept in `universe.py::FAILED_CANDIDATES`, not
deleted, because a "no" is as much a result here as a "yes."

### Usable (real ticker, plausible vol-index range, pre-2012-08 history)

| Market | Vol ticker | Equity ticker | Vol index range | Equity range |
|---|---|---|---|---|
| US (S&P 500) | `^VIX` | `^GSPC` | 1990-01-02 – 2026-07-24 (9208 obs) | 1990-01-02 – 2026-07-24 (9207 obs) |
| US (Nasdaq 100) | `^VXN` | `^NDX` | 2001-01-23 – 2026-07-24 (6413 obs) | 1990-01-02 – 2026-07-24 (9207 obs) |
| US (Dow) | `^VXD` | `^DJI` | 2005-11-22 – 2026-07-24 (5189 obs) | 1992-01-02 – 2026-07-24 (8701 obs) |
| India (Nifty 50) | `^INDIAVIX` | `^NSEI` | 2008-03-03 – 2026-07-23 (4504 obs) | 2007-09-17 – 2026-07-23 (4623 obs) |
| Australia (ASX 200) | `^AXVI` (A-VIX) | `^AXJO` | 2008-01-02 – 2026-07-23 (4692 obs) | 1992-11-23 – 2026-07-23 (8510 obs) |
| Europe (EURO STOXX 50) | VSTOXX (fixture) | `^STOXX50E` | 1999-01-04 – **2016-02-12, frozen** (4357 obs) | 2007-03-30 – 2026-07-23 (4840 obs) |

Only **four** country/index pairs (US, India, Australia, Europe) carry both a real
implied-vol index *and* pre-2012-08 history. US-Nasdaq and US-Dow are extra US
benchmarks, not distinct countries — reported as a within-US robustness check, not part
of the cross-market question. **India and Australia are the only two non-US, non-EU
markets found anywhere with a usable free volatility index.**

### Real ticker, but data starts after the break — excluded

| Market | Ticker | Coverage |
|---|---|---|
| Brazil ETF vol index (CBOE VXEWZ, via EWZ) | `^VXEWZ` | 2023-06-26 onward only |
| EAFE ETF vol index (CBOE VXEFA, via EFA) | `^VXEFA` | 2023-06-26 onward only |

CBOE publishes these against ETFs (`EWZ`, `EFA`), not the countries' headline indices,
and both only exist on Yahoo from mid-2023 — entirely post-break. Including them would
mean forcing a 2012-08 split onto data that starts eleven years later; excluded rather
than force-fit.

### Tried and not retrievable at all

Every one of these came back empty, delisted, 404, or (for three of them) a single
garbage row — confirmed by direct fetch, not assumed from memory:

`^VFTSE` (UK), `^VDAX`/`^V1XI`/`VDAXNEW.DE`/`^VDAXNEW`/`^V1X` (Germany), `^JNIV`/`^VXJ`/
`^N225VI` (Japan), `^VHSI` (Hong Kong), `^VKOSPI`/`^KOSPIVIX` (Korea), `^VSMI`
(Switzerland), `^VIBOVESPA`/`^VBOV` (Brazil), `^VIXC`/`^TSXVIX` (Canada), `^VXFXI`
(China), `^TVIX`/`^TAIEXVIX` (Taiwan), `^RVX` (US Russell 2000), `^VXEEM` (emerging
markets ETF), `^VXEWJ` (Japan ETF), `^V2TX`/`^VSTOXX` (VSTOXX direct — confirms
`eu_variance_premium`'s own finding that Yahoo carries no VSTOXX ticker at all). Full
list with per-ticker failure detail: `universe.py::FAILED_CANDIDATES`.

**Verdict on coverage alone:** free, no-signup data covers the US and exactly two other
countries (India, Australia) with real headline volatility indices, plus a short,
frozen European series. Yahoo Finance's free volatility-index coverage outside the US
is far thinner than the option-market literature might suggest — most of the "VIX-style"
national indices that do exist (VDAX-NEW, VHSI, VKOSPI, VSMI) are simply not on Yahoo.

## Module map

- `cross_market.py` — the one new statistic: `compare_break_changes`, a cross-sectional
  independent-samples z-test on two markets' `StructuralBreakResult.difference` values.
  No I/O.
- `market_history.py` — `probe_ticker` (empirical retrievability check, feeds the
  coverage table above and `--probe`) and `load_market` (pairs one market's vol-index
  level series with its equity index's log returns), both thin wrappers over
  `eu_variance_premium.yahoo_history`'s generalized loader.
- `universe.py` — the market list (`MARKETS`), and the full probe log of what was tried
  and failed (`FAILED_CANDIDATES`, `TOO_SHORT_FOR_A_PRE_2012_COMPARISON`).
- `__main__.py` — the report shell. `--probe` (default) prints only the coverage table
  above, live. `--live` runs the actual pre/post-2012-08 comparison.

Run it from the repository root:

```bash
.venv/bin/python -m _prototyping.global_variance_premium          # --probe: coverage only
.venv/bin/python -m _prototyping.global_variance_premium --live   # the actual comparison
```

There is no synthetic mode here (unlike `eu_variance_premium`): the structural-break
mechanism was already verified there against a known synthetic gap. This prototype's
job is establishing what real free data covers and shows, which synthetic data cannot
speak to.

**One specification only.** Break date `2012-08-01` (DBG's own dated break, not
searched over), a 21-trading-day forward realized-vol horizon (the 30-calendar-day
constant maturity all of `^VIX`/`^VXN`/`^VXD`/VSTOXX/`^INDIAVIX`/`^AXVI` are documented
to share — verified against each index's own primary-source methodology description for
VIX and VSTOXX in `eu_variance_premium`; taken as given, not independently re-verified
to that depth, for `^INDIAVIX` and `^AXVI` here), and Newey-West lags = horizon − 1 = 20.
Applied identically to every market — no break date, horizon, or lag count was tuned
per market or searched over.

## Real result (`--live`, run 2026-07-25)

```
US (S&P 500)  (^VIX / ^GSPC)
  break date: 2012-08-01
  pre  [ 5692 obs]: mean=+4.46 vol-pts  se=0.31  t=+14.21  p=0.0000
  post [ 3493 obs]: mean=+3.50 vol-pts  se=0.47  t=+7.50   p=0.0000
  change (post - pre): -0.96 vol-pts  t=-1.71  p=0.0877

US (Nasdaq 100)  (^VXN / ^NDX)
  pre  [ 2899 obs]: mean=+4.95 vol-pts  post [ 3493 obs]: mean=+2.61 vol-pts
  change (post - pre): -2.34 vol-pts  t=-3.02  p=0.0025

US (Dow)  (^VXD / ^DJI)
  pre  [ 1679 obs]: mean=+2.98 vol-pts  post [ 3489 obs]: mean=+3.18 vol-pts
  change (post - pre): +0.20 vol-pts  t=+0.22  p=0.8244

India (Nifty 50)  (^INDIAVIX / ^NSEI)
  pre  [ 1076 obs]: mean=+4.16 vol-pts  post [ 3391 obs]: mean=+2.55 vol-pts
  change (post - pre): -1.61 vol-pts  t=-1.34  p=0.1811

Australia (ASX 200)  (^AXVI / ^AXJO)
  pre  [ 1151 obs]: mean=+5.38 vol-pts  post [ 3513 obs]: mean=+1.53 vol-pts
  change (post - pre): -3.85 vol-pts  t=-4.10  p=0.0000

Europe (EURO STOXX 50 / VSTOXX)  (V2TX fixture / ^STOXX50E)
  pre  [ 1334 obs]: mean=+3.52 vol-pts  post [  858 obs]: mean=+2.19 vol-pts
  change (post - pre): -1.33 vol-pts  t=-1.08  p=0.2820

Cross-market comparison (reference: US S&P 500)
  US -0.96 vs India      -1.61 vol-pts  (difference -0.65, z=-0.49, p=0.6248)
  US -0.96 vs Australia  -3.85 vol-pts  (difference -2.88, z=-2.64, p=0.0084)
  US -0.96 vs Europe     -1.33 vol-pts  (difference -0.37, z=-0.27, p=0.7868)
```

Europe's numbers match `eu_variance_premium`'s own already-published `--live` result
exactly (pre +3.52/post +2.19/change -1.33, p=0.2820) — expected, since both call the
same fixture and the same `structural_break_test`; included here as a reuse-consistency
check, not a new measurement.

## Verdict

**On this raw-gap proxy, the flattening is not uniquely American — and where it *is*
distinguishable from the US, the other market flattened more, not less.**

- The US's own raw gap declined only marginally: -0.96 vol-pts, significant at 10% but
  not 5% (p=0.088). It stayed solidly positive both before and after the break
  (p < 0.0001 each side) — consistent with the "raw gap ≠ alpha" limitation above: DBG's
  *alpha* went to zero; the raw gap here did not, it just narrowed a little.
- That US result is **not stable across US benchmarks**: Nasdaq's gap declined sharply
  and significantly (-2.34, p=0.0025); Dow's did not decline at all (+0.20, p=0.82, wrong
  sign if anything). Even restricted to "did the US flatten," the answer already depends
  on which US index is used.
- Of the three non-US markets, only Australia's change is statistically distinguishable
  from the US's (z=-2.64, p=0.0084) — and Australia's decline (-3.85 vol-pts, p<0.0001)
  is **larger**, not smaller, than the US's. India (p=0.62) and Europe (p=0.79) are
  statistically indistinguishable from the US's own modest decline.
- Put together: the strongest, cleanest structural break in this whole panel belongs to
  **Australia**, a market with a far smaller option-selling-vehicle footprint than the
  US. That is the opposite of what the vehicle-driven compression story (BIS Quarterly
  Review March 2024; Calvet/Celerier/Liao/Vallée; Park/Kurucak) would predict if vehicle
  AUM were the dominant driver here — this dataset does not support "compression
  concentrated where vehicles are large," though it also cannot rule the mechanism out:
  vehicle AUM was explicitly out of scope and not measured, and a raw gap conflates true
  premium compression with pure beta-compensation drift for reasons unrelated to
  vehicles entirely.
- **Confound to flag, not resolved:** India's and Australia's pre-2012 windows are short
  (4.4-4.6 years, 2007/2008-2012) and dominated by the 2008 crisis and its aftermath,
  while the US S&P 500 window runs a full 22.5 years back to 1990. A pre-mean that is
  mechanically inflated by crisis-era vol would produce a mechanically larger "decline"
  at the break that has nothing to do with a genuine 2012-specific structural change.
  This does not obviously explain Australia's result on its own (Australia's pre-mean,
  +5.38, is the highest in the panel, but Europe's pre-mean over an equally short and
  equally crisis-loaded window, +3.52, is the lowest) — so the confound is real and
  disclosed, not confirmed as the explanation.
- Given all of this, the honest summary is **"no clean pattern, and free data covers too
  few markets to resolve it further"** — one of the two outcomes flagged as likely
  before running anything. It is not "everyone flattens" (Dow and, weakly, the US S&P
  500 barely moved; India is ambiguous) and it is not "only the US flattens" (Australia
  flattened harder and more cleanly). What this design **can** say: the US raw gap is
  not obviously an outlier among the four markets free data allows testing. What it
  **cannot** say: anything about DBG's actual claim (a risk-adjusted alpha going to
  zero), which no market's free data here supports computing.
- One specification was run throughout (stated above); nothing was tuned to produce
  significance in either direction.

# PROTOTYPE — European variance risk premium after 2012

> **Read this before the numbers below:** the only free VSTOXX source found for this test
> is frozen at **2016-02-12** (see "What free data exists" below). Every result in this
> document is silent on **2016-2026** — the decade that actually matters for "is the
> premium dead *now*." A positive or flat gap through early 2016 is not evidence about
> today.

## Question

Dew-Becker & Giglio (Chicago Fed WP 2025-17) find that the US index-option variance risk
premium's CAPM alpha — measured on 5% OTM S&P 500 puts and ATM straddles — collapsed to a
value indistinguishable from zero at a structural break dated August 2012. Garleanu,
Pedersen & Poteshman (RFS 2009) show the premium's sign varies by venue, so that US result
does not automatically transfer to Europe. Nobody has run the same test on European
instruments. Our prior is that it's dead here too; this prototype's job is to establish
that cleanly, or to find that it isn't.

This is a throwaway data-analysis prototype, not an interactive state-machine TUI (the
question is statistical, not a state model to press buttons through). It follows this
repo's `etf_cluster_reversal` prototype's shape instead: pure statistics in `model.py`,
one module per external data boundary, a deterministic-synthetic default mode for
mechanism verification, and a `--live` flag for the real verdict.

Run it from the repository root:

```bash
.venv/bin/python -m _prototyping.eu_variance_premium          # synthetic, no network
.venv/bin/python -m _prototyping.eu_variance_premium --live    # SX5E fetched live via
                                                                # yfinance; VSTOXX read
                                                                # from the bundled fixture
```

## What free data exists (and what doesn't)

**No free investable EURO STOXX 50 put-write series exists.** STOXX does publish a
genuine put-write (not buy-write/covered-call) index — `SX5E3P`, ISIN CH0106231670,
"1-EURO STOXX 50® PutWrite" — confirmed at `stoxx.com/index/sx5e3p/`. But:

- its own factsheet (`stoxx.com/download/indices/factsheets/SX5E3P.pdf`) discloses that
  reported history includes **backtested, pre-launch, hypothetical performance** — exactly
  the backfill contamination this test needs to rule out, and STOXX's cert/site issues
  (below) made the factsheet itself unfetchable to confirm the real launch date;
- no downloadable free daily series for `SX5E3P` could be found (STOXX's historical-data
  distribution mechanism, below, does not carry it — only `V2TX`);
- no UCITS ETF or ETN tracking `SX5E3P` exists (checked justETF/ETF databases and this
  repo's own prior scratchpad probe, `scratchpad/vrp_probe.py`, which independently
  concluded "no put-write UCITS" while researching a different question).

So the rigorous test — regress a put-write index's excess returns on the index, get a
CAPM alpha, test for a break — **cannot be replicated on free data.** This prototype
instead runs the weaker fallback the brief anticipated: a **raw** VSTOXX-minus-realized-
SX5E-volatility gap. That gap is explicitly *not* a risk-adjusted alpha — a positive gap
fully explained by market beta is compensation for holding the index, not income — and
every report the prototype prints says so.

**VSTOXX has no Yahoo Finance ticker at all.** Yahoo's own quote-search API
(`query1.finance.yahoo.com/v1/finance/search?q=VSTOXX`) returns zero matching quotes.
Every ticker guessed from community references — `V2TX.DE`, `^V2TX`, `OVS.EX`,
`^VSTOXX` — comes back delisted/empty through `yfinance`. The only free source found is
STOXX's own historical-data file:

```
https://www.stoxx.com/document/Indices/Current/HistoricalData/h_vstoxx.txt
```

Two things about this source carry into every verdict built on it:

1. **`www.stoxx.com` serves this file with an incomplete TLS certificate chain** — the
   identical "unable to get local issuer certificate" failure was independently
   reproduced against two unrelated HTTP clients (this repo's WebFetch tool and a plain
   Python `requests` call), so it's STOXX's server misconfiguration, not a local
   trust-store problem. The prototype originally fetched this file live on every run with
   certificate verification disabled for that one host/path. That bypass has been
   **removed** — a prototype is exactly the kind of place an unverified-connection pattern
   gets copied from, and it bought nothing anyway once point 2 below is accounted for.
   Instead, `fixtures/h_vstoxx.txt` is a byte-for-byte checked-in copy of the response,
   fetched **2026-07-25**, with its checksum recorded next to it in `stoxx_history.py`
   (`FIXTURE_SHA256 = "4b4076135a5f5817794c5f8cb44858e2475a7ac81b198f1a43e4174bd961b76b"`,
   verified against the file's raw bytes on every load). Anyone can fetch the URL above
   themselves and run `sha256sum` on the result to confirm it matches what's checked in.
2. **The file is frozen at 2016-02-12.** STOXX appears to have retired this free
   distribution mechanism after that date in favour of a subscriber-only quotes API
   (`quotes.stoxx.com`, confirmed to return `401 Unauthorized` without an API key). Since
   the file cannot change, checking in a snapshot loses nothing relative to fetching it
   live — but it also means, as stated at the top of this document, that nothing below
   speaks to 2016-2026.

EURO STOXX 50 itself (`^STOXX50E`) is a normal Yahoo Finance / `yfinance` ticker with no
such problems; `yfinance` is already an aegis-rd dependency (used elsewhere as the FX
gap-fill provider), reused here rather than hand-rolling a Yahoo scraper. Its history via
Yahoo starts 2007-03-30, which — intersected with VSTOXX's 1999-2016 window — sets the
real usable test window to **2007-04-02 through 2016-01-14** (the last date with a full
21-trading-day forward window before VSTOXX's data ends).

**Moneyness concentration is untestable on free data.** VSTOXX is one constant-maturity,
near-the-money-ish implied-vol point, not a moneyness-sliced surface. No free source of
European index-option implied volatility by strike was found.

## Module map

- `model.py` — pure functions: forward-matched realized variance, the VSTOXX-vs-realized
  gap, a Newey-West (HAC) mean test, the pre/post structural-break test, a slow (12-month)
  trend overlay, and the loss-state-timing check. No I/O.
- `stoxx_history.py` — read, checksum-verify, parse, and validate the checked-in VSTOXX
  fixture (`fixtures/h_vstoxx.txt`). No network fetch — see the caveats above for why.
  Still takes an injectable `fetch: Callable[[], str]` so tests can supply their own
  sample text without touching the filesystem default.
- `yahoo_history.py` — fetch, cache, and validate daily closes/log-returns for any
  Yahoo Finance ticker via `yfinance` (used here for EURO STOXX 50; generalized so the
  sibling `global_variance_premium` prototype reuses it for other markets' tickers
  instead of a second hand-rolled loader). Injectable `loader` for the same reason as
  above; a simple on-disk parquet cache under `.cache/` avoids refetching on every run.
- `synthetic.py` — deterministic synthetic VSTOXX/SX5E-like series with a *known*
  embedded gap, so a reader can watch the structural-break test correctly recover a
  number it was never told, without touching the network. Mechanism check only — not
  evidence about Europe.
- `__main__.py` — the report shell. Default mode is synthetic; `--live` fetches real SX5E
  data and pairs it with the checked-in VSTOXX fixture.

## The real result (`--live`, run 2026-07-24)

Re-run 2026-07-25 after switching VSTOXX from a live TLS-bypassed fetch to the checked-in
fixture below — output unchanged, as expected for a source that has not changed since 2016.

```
VSTOXX (V2TX): 4357 sessions, 1999-01-04 to 2016-02-12 (STOXX, frozen — not updated)
^STOXX50E: 4839 sessions, 2007-04-02 to 2026-07-23 (Yahoo Finance)

Test 1 — raw VSTOXX-minus-realized-SX5E variance gap
  break date: 2012-08-01
  pre  [1334 obs]: mean=+3.52 vol-pts  se=1.03  t=+3.43  p=0.0006
  post [ 858 obs]: mean=+2.19 vol-pts  se=0.69  t=+3.20  p=0.0014
  difference (post - pre): -1.33 vol-pts  t=-1.08  p=0.2820

Test 4 — loss-state timing vs. a slow (12-month) trend overlay
  full-sample correlation (short-vol payoff, trend): -0.003
  trend mean return on short-vol's worst 5% (99 days): -0.0822% vs full-sample -0.0180%
  trend positive on 47% of those worst days
```

## Verdict

**Untestable, rigorously — the free-data proxy says "not obviously dead," but the proxy
is weak and the window is short.**

- The rigorous test (put-write CAPM alpha + structural break) cannot be run at all on
  free data: no series, no wrapper, and STOXX's own factsheet flags backtest
  contamination in the one index that would matter.
- The raw gap (VSTOXX minus forward-realized SX5E volatility) was **significantly
  positive both before and after August 2012** (+3.52 and +2.19 vol points, both
  p < 0.01), and the *change* across the break is **not** statistically significant
  (p = 0.28). On this proxy, Europe shows no sign of the US collapse — but:
  - this is a raw gap, not risk-adjusted alpha. A persistently positive gap is equally
    consistent with "a genuine premium survived" and with "this was always pure beta
    compensation, never risk-adjusted out" — Dew-Becker & Giglio's finding is specifically
    that the *alpha* went to zero, and we have no way to compute alpha here;
  - the free VSTOXX data goes dark in February 2016, so this only covers ~3.5 years
    post-break. It says nothing about whether any premium survived into 2016-2026 — the
    decade that actually matters for "is this dead now";
  - the Calvet-Celerier-Liao-Vallée structured-product compression story (dealers less
    short downside convexity → less premium demanded) would predict a *smaller* gap in
    Europe than the US, not persistence — the raw numbers here don't obviously support
    that mechanism either, but a raw gap can't isolate it from beta compensation.
- Moneyness concentration: untestable, no free surface data.
- Loss-state timing: weak evidence against clean diversification. Correlation between
  the short-vol payoff proxy and the slow-trend overlay is ~0, but on short-vol's worst
  5% of days trend's mean return was also negative (-0.08% vs -0.02% full-sample) and
  positive only 47% of the time — consistent with the prior that fast vol spikes hurt
  both sleeves together, though this is a single-index proxy, not the live trend
  strategy.

**Bottom line:** free data cannot confirm or refute the US-style collapse for Europe.
The best available proxy shows no significant change around August 2012 through early
2016, which is evidence *against* an immediate European collapse on this narrow window,
but it is silent on the last decade and cannot separate a real premium from pure beta
exposure. Answering this properly needs either a paid options/IV-surface data feed or a
directly obtained (not backtested) `SX5E3P` series from STOXX under a commercial
license — both out of scope for "free data only."

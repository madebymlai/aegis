# Continuous-futures contract eligibility by volume liquidity leadership

## Context

The continuous series rolled *through* thin serial months (e.g. COMEX gold's May/
July serials, GCK4/GCN4) because the contract calendar admitted every listed
outright and the pure expiry roll chained through all of them. We need data-driven
eligibility — no hardcoded per-product month cycle — so the series holds only the
contracts a desk actually trades. (Discovered from aegis-rd-voy / aegis-rd-5mp.)

## Decision

A dated contract is eligible for the **Liquid Cycle** iff it is ever the
**Liquidity Leader** — the contract with the highest daily volume *smoothed over the
derived roll-lead window* (`roll_lead_days`) among the contemporaneously-live contracts
of its root — at some point in its own life. Eligibility is measured from
the OHLCV legs we already pull; the pure calendar roll (`roll.roll_schedule`) then
runs **unchanged** on the eligible set. Volume governs **inclusion only**; roll
**timing** stays on the calendar.

Eligibility is judged on **daily** volume regardless of the requested bar cadence: the
ranking probe is an `ohlcv-1d` pull of all candidates, while the deliverable legs are
fetched at the request cadence for the eligible contracts only (serials never
materialize at an intraday cadence). Per-bar (e.g. 1h) leadership is not used — it
would inject intraday noise into a low-frequency inclusion decision and make
eligibility depend on the sampling cadence. The 1d candidate bars are retained as 1d
Raw Futures Legs via the existing presence-cache, so the probe is paid once and reused.

Leadership is judged on volume **smoothed over the derived roll-lead window**
(`roll_lead_days`), not a single day's argmax. A single-day max is an extremum,
vulnerable to one anomalous print (an expiry-day or roll-spread spike) falsely admitting
a **Serial Month**; the literature never decides a dominant contract on one raw day
(2-day confirmation, margin buffers) because volume is a noisy flow. Smoothing over the
roll-lead window — the liquidity-migration window already derived from cadence — hardens
the rule with **no new knob** and no fitted lookback (which the literature warns
against). It is a no-op where domination is systematic (gold serials never lead) and
bites only for genuinely marginal products.

## Why volume, not open interest

Open interest is the textbook inclusion signal, but Databento's `statistics` schema
(its only OI source) streams in **22–64 s** — it returns all stat types with no
server-side filter — versus **~2 s** to read volume from the OHLCV legs we already
fetch. On live GC 2024-05-01..2024-08-01 both signals produced the **identical**
Liquid Cycle (`GCM4, GCQ4, GCZ4`; the May/July serials led **0 days**). Volume's only
weakness vs OI is day-to-day crossover noise, which affects roll **timing** — and
timing is the calendar's job, not volume's — so the noise is immaterial to an
inclusion-only use. Volume also keeps **one data path** (no statistics schema, no
eligibility cache) and dissolves the OI-coverage "fail-open" question, because volume
shares the bars' own coverage.

## Considered options

- **OI via `statistics`** — rejected on latency (22–64 s per derivation) and the
  second I/O path + decision cache it would force.
- **Databento `{ROOT}.n.0` OI-ranked continuous symbology** — rejected: `continuous
  → raw_symbol` is unsupported (HTTP 422), it couples inclusion to a proprietary
  feature, and it won't reproduce on the live (IBKR) side that `assert_roll_agreement`
  guards.
- **Liquidity-crossover roll** (volume/OI drives the roll *date* too) — rejected: it
  breaks `roll.py`'s purity and the research/live roll-schedule agreement. We use
  volume for inclusion only.

## Consequences

- The in-window candidate legs (serials included) are still fetched once to rank
  them, then excluded from the roll — they remain cached-but-unused source material.
  No regression: the pipeline fetched them before; it just no longer rolls through
  them.
- aegis-rd-voy's non-print tolerance stays — a liquid series still hits venue
  holidays; this decision removes the serials that made those non-prints bite.

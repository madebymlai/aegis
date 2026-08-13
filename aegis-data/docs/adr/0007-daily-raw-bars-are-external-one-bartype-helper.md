# Daily Raw Bars are EXTERNAL, behind one BarType helper in aegis-data

Status: accepted

## Context

A `BarType`'s `AggregationSource` is part of its identity — and part of the
catalog's on-disk path. `ParquetDataCatalog` stores bars under
`data/bar/{full_bar_type}/…` (verified by writing through our own catalog and
listing the directory), so `…-LAST-INTERNAL` and `…-LAST-EXTERNAL` are *different
folders* for the same instrument that never meet.

Nautilus defines `EXTERNAL` as "aggregated by a venue or data provider" and
`INTERNAL` as "the DataEngine subscribes to ticks and aggregates locally." Our
Catalog is vendor-provided daily OHLCV (IBKR historical; the future Databento
futures seed) — finished bars the vendor aggregated, with no tick feed to build a
multi-year daily series from. They are `EXTERNAL` by definition. Live also
*structurally requires* `EXTERNAL`: that is how the node receives IBKR's completed
daily bar, which the next-close execution model then consumes.

Yet the catalog labelled bars `…-LAST-INTERNAL` (`raw_bar_type`: 1D-only, returns
a `str`) while the trader correctly used `…-LAST-EXTERNAL` (`data/bar_type.py`:
general timeframe parsing, fail-closed, returns a `BarType`). Two helpers, two
answers, for the same instrument — the r8b divergence encoded in the identifier
and split across two on-disk folders.

## Decision

- **Canonical aggregation source is `EXTERNAL` everywhere** — catalog write/read,
  RD load, backtest load, live subscribe, and the lazy fill.
- **Price type is `LAST`, except cash FX is `MID`.** Cash FX (a `CurrencyPair`,
  e.g. `EUR/USD.IDEALPRO`) has no trades print: IBKR serves MIDPOINT/BID/ASK on
  IDEALPRO, not TRADES, so a `LAST` (`whatToShow=TRADES`) historical request fails
  with IB error 162 ("no historical market data"). FX raw bars are therefore
  `MID-EXTERNAL`; everything else stays `LAST-EXTERNAL`. The carve-out is decided
  inside `raw_bar_type` as a pure function of the `InstrumentId` — an FX pair is
  recognised by its `BASE/QUOTE` symbol shape, the one signal available before the
  instrument definition is resolved (on a cold fill the definition is seeded only
  *after* the bars are fetched, so the asset class is not yet known at request
  time). Deciding it in the one helper keeps write and read on a single identity:
  FX keys as `…-MID-EXTERNAL` on both the fill/write and the warm read, and cannot
  desync. (Idiomatic precedent: the Nautilus IB adapter already carves the price
  type by instrument — `venue == "PAXOS"` + `LAST → AGGTRADES`.)
- **One `raw_bar_type` helper lives in aegis-data**, the shared lower context that
  both RD and the trader depend on (it depends on neither, so the helper cannot
  live in the trader). The trader's superior implementation — general timeframe
  parse, fail-closed, returning a `BarType` — is **relocated down** into aegis-data,
  replacing the 1D-only/`str`/`INTERNAL` version. aegis-data's catalog code
  stringifies it only at the Nautilus query/identifier boundary. The trader imports
  it and deletes its local construction. `resolve_book_timeframe` (a
  commingled-book/sleeves rule, not bar identity) stays in the trader.

## Considered and rejected

- **Make everything `INTERNAL` instead.** Not viable: live can only receive IBKR's
  finished daily bars via an `EXTERNAL` subscription; `INTERNAL` would ask Nautilus
  to aggregate a daily bar from a tick feed it does not have.
- **Keep two helpers, or make the trader's the canonical one.** The trader is the
  higher layer, so aegis-data could not import it; and a second helper is exactly
  the desync vector this removes.

## Consequences

- The on-disk bar folder name becomes `…-LAST-EXTERNAL` (`…-MID-EXTERNAL` for cash
  FX). Free now — nothing durable is seeded (only throwaway test fixtures); after
  r8b.3 seeds depth and live captures forward it would be a re-seed.
- Catalog, RD, backtest, live, and the lazy fill share one `BarType` per
  instrument; they cannot desync again.
- A future reader might "fix" daily `EXTERNAL` to `INTERNAL` (Nautilus recommends
  `INTERNAL` for *intraday* on some venues). This ADR records why *daily* is
  `EXTERNAL`: there is no tick feed, and live must subscribe `EXTERNAL`.

## Amendment (aegis-rd-tggo.2, sharpened by aegis-rd-t2kc): the price type is a declared mark mode, not a symbol heuristic

The symbol heuristic ("`LAST`, except cash FX is `MID`") is superseded
entirely as a resolution rule. Each leg now has a declared **mark mode** — a
closed three-value set, resolved per instrument by
`aegis_data.marking.DeclaredMarkingResolver` into an `InstrumentMarking` value
object (the one seam every raw bar-type consumer crosses):

- **`LAST`** (the only default: no declaration means LAST) — one
  `LAST-EXTERNAL` bar, marked at its close. Continuous-future legs are `LAST`
  by construction (this carve-out is unchanged; the continuous target
  `BarType` is not a marking decision).
- **`MID`** (bar-marked) — one `MID-EXTERNAL` bar, marked at its close. Cash
  FX reaches this **structurally**: an `exchange:` conversion leg is MID
  *because the config section that names it says what it is* (IBKR serves no
  TRADES print for cash FX); a *tradeable* FX pair declares `:MID` explicitly
  like any other mode, and a forgotten declaration fails loud at the gateway
  (IB error 162), never silently.
- **`QUOTE`** (quote-marked) — the instrument carries **`BID-EXTERNAL` +
  `ASK-EXTERNAL`** bars; its mark is the **derived** mid `(bid + ask) / 2`
  (`InstrumentMarking.reference_price`, the single home of the mid formula).
  This is the thin-ETF mode: trades are sparse but the vendor quote is dense.

The declaration is **one token where the instrument is named**
(`UEQC.IBIS:QUOTE`, `:MID`) or, for conversion legs, the `exchange:` section
membership itself — per-instrument scope, parsed once at config load, never a
maintained side table, never a runtime probe, and never a symbol-shape guess.
(`raw_bar_type` is LAST-only — the undeclared default; every other price type
keys through `external_bar_type` from a declaration, fixtures included, so
the `BASE/QUOTE` shape is consulted nowhere.)

**Architectural constraint (verified against the Nautilus backtesting docs),
the reason QUOTE derives its mid:** `EXTERNAL` L1 bars feed the simulated
venue's order book; `INTERNAL`/strategy-side values never touch the book. A
quote-marked instrument must therefore **never** also carry a `MID-EXTERNAL`
bar — it would enter the venue book as a zero-spread update and conflict with
the real BID/ASK spread the fills must pay. The mid is derived strategy-side
from the same BID/ASK series, so the mark and the fill share one source and
are consistent by construction. Enforced structurally: the resolver is the
only builder of `mark_bars` and emits `BID`/`ASK` for `QUOTE`.

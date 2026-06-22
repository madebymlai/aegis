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
corpus is vendor-provided daily OHLCV (IBKR historical; the future Databento
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

- **Canonical aggregation source is `LAST-EXTERNAL` everywhere** — catalog
  write/read, RD load, backtest load, live subscribe, and the lazy fill.
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

- The on-disk bar folder name becomes `…-LAST-EXTERNAL`. Free now — nothing durable
  is seeded (only throwaway test fixtures); after r8b.3 seeds depth and live
  captures forward it would be a re-seed.
- Catalog, RD, backtest, live, and the lazy fill share one `BarType` per
  instrument; they cannot desync again.
- A future reader might "fix" daily `EXTERNAL` to `INTERNAL` (Nautilus recommends
  `INTERNAL` for *intraday* on some venues). This ADR records why *daily* is
  `EXTERNAL`: there is no tick feed, and live must subscribe `EXTERNAL`.

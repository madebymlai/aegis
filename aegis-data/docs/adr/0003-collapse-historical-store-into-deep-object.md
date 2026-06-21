# Collapse the Historical Store into a deep HistoricalStore

Status: accepted (implemented)

## Context

ADR-0002 moved expected-bar coverage into the pure, frame-in
`StoreCoverage` module and left `store.py` as the owner of parquet I/O. After
that split, the store still exposed a wide free-function surface: path helpers,
write helpers, merge/replace helpers, read helpers, coverage-gap helpers, and
admission helpers repeated across native bars, FX rates, and Raw Futures Legs.

That surface forced callers to thread `store_dir` through every operation and
made the parquet layout part of tests and pull implementations. It also kept a
path plus row-count reporting step alive even though a row count is weaker than
a coverage-checked read: it can pass with NaNs, missing arrays, or off-grid
substitution.

## Decision

Collapse store I/O into one `HistoricalStore` value object. The object owns the
store root, parquet path scheme, admitted parquet format, coverage checking,
and write semantics. Public covered-history operations are:

- `read(key, window)`
- `write(key, frame, window, mode=WriteMode...)`
- `coverage_gaps(key, window)`
- `assert_admissible(key, frame, window)`

`CoveredWindow` carries timeframe, start, end, arrays, calendar, and listed
adjustment as one value. Covered reads and writes use one `pd.DataFrame` shape;
FX history is a `rate` column at the storage boundary.

Raw Futures Legs remain a sibling source-material contract on the same object:
`merge_leg`, cold-tolerant `read_leg`, `record_leg_coverage`, and
`read_leg_coverage`. They do not expose replace or overwrite modes because raw
legs are immutable provider source material.

The module keeps `data_dir()` as the OS-root resolver and `raw_futures_dir()` as
a display helper for the CLI. The public parquet path helpers, covered row
count, multi-key reads, free write helpers, and free admission helpers are
deleted.

## Consequences

- Pulls and readers construct a store once and tell it what to do by identity.
- Store tests seed through `write(..., OVERWRITE)` and assert through `read` or
  `coverage_gaps`, not public paths or row counts.
- Databento continuous futures use `WriteMode.REPLACE` so re-derived adjusted
  spans overwrite while outside bars remain.
- yfinance gap fills use `WriteMode.MERGE` so already-admitted provider facts
  win on overlap.
- The on-disk parquet layout is unchanged; only the in-process interface was
  collapsed.
- No `CONTEXT.md` change is needed because the change reuses existing domain
  vocabulary: Historical Store, Covered History, Store Read, Native Market
  Bars, FX History, and Raw Futures Leg.

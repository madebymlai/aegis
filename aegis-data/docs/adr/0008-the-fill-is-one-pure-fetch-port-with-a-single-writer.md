# The catalog fill is one pure-fetch port with a single writer; definitions are a separate Step-1 write

Status: accepted

## Context

ADR-0006 settled that the lazy fill is unconditional and shared. This ADR settles
its *shape* — the seam between aegis-data and the IBKR adapter — because the
existing draft conflated several concerns:

- `NautilusDataProviderPort.request_bars(..., update_catalog=True)` told the
  *provider* to persist, while `CatalogBackedDataPort` *also* wrote the returned
  bars — a double-write with ambiguous ownership.
- The catalog needs the `Instrument` *definition*, not just bars: the trader
  backtest calls `catalog.instruments(...)` and fails loud if any is missing. The
  tempting fix was to widen the port with a second method, `request_instruments`.

## Decision

- **The port is a single, pure-fetch method.** `request_bars(bar_type, *, start,
  end) -> Sequence[Bar]` — a query, no `update_catalog` side effect. The catalog's
  write format, the `EXTERNAL` identity (ADR-0007), the window, and the
  additive-monotonic merge are `CatalogBackedDataPort`'s secret; it is the **single
  writer of record** (CQS + Information Hiding). This matches Nautilus's standalone
  `HistoricInteractiveBrokersClient`, which *returns* bars for the caller to write.

- **Do not widen the port for instrument definitions.** Definitions are a separate
  **Step-1 write**, not per-window fill data — which is also how Nautilus models it:
  `request_instruments` and `request_bars` are *separate* calls, and the blessed
  loaders write `instruments` first, then bars (`catalog.write_data(instruments)`
  then `write_data(bars)`). Live gets definitions via the IB InstrumentProvider
  (`load_ids`) into the cache and the configured catalog; RD/backtest gets them via
  a one-time `request_instruments → write_data`, or from the r8b.3 seed. Resolving a
  definition is the unavoidable prerequisite to fetching any bar, so the invariant
  **bars for an InstrumentId ⇒ its definition is in the catalog** holds for free —
  and RD's fill must persist definitions even though RD's vbt read never uses them,
  because the *same corpus* serves the trader backtest, which does.

- **One merge primitive.** The lazy fill and the `aerd backfill` ingester (r8b.3)
  share one write/merge rule: additive `consolidate_data(deduplicate=True)` that
  never overwrites; a bounded-window overwrite is reachable only through an explicit
  `--force --start --end`. Routine and operator writes cannot drift into two merge
  semantics.

## Considered and rejected

- **Widen the port with `request_instruments`.** Rejected (ISP): it grows a port
  that should stay one deep method, and it contradicts Nautilus, which keeps the two
  as separate operations. Definitions belong to a different lifecycle (static setup,
  not windowed fill).
- **The provider owns the write (`update_catalog=True`).** Rejected: it pushes the
  catalog's write format, identity, and merge knowledge into *every* adapter (DRY /
  Information Hiding), and it is a command fused into a query (CQS). The provider
  returns data; aegis-data writes it.

## Consequences

- A future reader who wants "the provider to just write" or "a `request_instruments`
  on the port" has a recorded reason not to: one writer, one pure-fetch method.
- The catalog partitions one folder per `bar_type`, so a partial-instrument write
  cannot clobber other instruments (a known hazard for bucketed parquet caches). Do
  not consolidate multiple instruments into shared files.

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

- **Distribution reads are verified catalog-port reads.** The corpus is
  self-describing for distributions as well as bars: for any distribution-capable
  `InstrumentId`, `CatalogBackedDataPort.distributions(...)` must prove the bounded
  request window has been checked against an adjusted-last source before it returns
  stored `Distribution` rows. A direct `query_distribution_data(...)` is a low-level
  storage primitive, not a research or trader read path.

- **Distribution coverage uses a marker-row ledger.** Verification writes a
  `DistributionCoverageMarker` interval through the same catalog interval machinery
  used by bar coverage, including the zero-event case where the adjusted-last series
  proves that no distributions occurred. The marker carries the instrument, whether
  the instrument was applicable, the checked-at timestamp, and the event count for
  the verified interval. Routine reads are warm once marked; a bounded
  force-reverify is the explicit operator path for IBKR restatements, and rewrites
  only that requested distribution window before stamping a fresh marker.

- **Applicability has exclusion polarity.** Stored catalog definitions decide whether
  distribution verification applies. Known exclusions, such as futures contracts and
  synthetic continuous-future roots resolved from dated legs, are marked
  not-applicable. Unknown instruments fail loud instead of being treated as
  not-applicable, so a missing definition cannot silently bypass verification.

- **Research and trader cross one enforcement seam.** Aegis RD and Aegis Trader both
  obtain distributions through `CatalogBackedDataPort.distributions(...)`. RD records
  the coverage report in provider metadata for quality evidence; Trader feeds the
  same verified distributions into the backtest engine. Neither context owns a
  parallel distribution reader.

## Considered and rejected

- **Widen the port with `request_instruments`.** Rejected (ISP): it grows a port
  that should stay one deep method, and it contradicts Nautilus, which keeps the two
  as separate operations. Definitions belong to a different lifecycle (static setup,
  not windowed fill).
- **The provider owns the write (`update_catalog=True`).** Rejected: it pushes the
  catalog's write format, identity, and merge knowledge into *every* adapter (DRY /
  Information Hiding), and it is a command fused into a query (CQS). The provider
  returns data; aegis-data writes it.
- **Use an empty distribution write as the coverage ledger.** Rejected: empty writes
  are exactly the zero-event proof case, and the storage writer has no file to extend
  when no `Distribution` rows exist. That would silently leave no interval for
  `get_missing_intervals_for_request(...)`, so zero-event verified windows would look
  unverified forever. A marker row makes "checked and empty" first-class catalog
  data instead of a filename side channel.

## Consequences

- A future reader who wants "the provider to just write" or "a `request_instruments`
  on the port" has a recorded reason not to: one writer, one pure-fetch method.
- **How "RD's fill must persist definitions" is honoured without widening the port:**
  a successful backfill (a miss the provider served) triggers an *idempotent*
  definition Step-1 write through a **separate injected seeder**
  (`CatalogBackedDataPort.definition_seeder`), not a port method. The seeder
  (`seed_instrument_definitions`) writes only the definitions missing from the
  catalog, so it is free when they are already present — which is why it can fire on
  the fill yet a *warm* read (a cache hit, no miss) never seeds and never connects.
  The bar port stays a single pure-fetch method; definitions remain a distinct
  lifecycle, merely *triggered* at the point a new instrument is first served.
- The catalog partitions one folder per `bar_type`, so a partial-instrument write
  cannot clobber other instruments (a known hazard for bucketed parquet caches). Do
  not consolidate multiple instruments into shared files.

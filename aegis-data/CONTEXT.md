# Aegis Data

Shared market-data context for Aegis RD and Aegis Trader. It owns the durable
Catalog and the port-backed read/fill behavior used by both research and live.

## Language

**Catalog**:
The durable home of every record this context owns, rooted under the `aegis-data`
OS data directory (`AEGIS_DATA_DIR` override, then `catalog/`). Records keep
`ParquetDataCatalog`'s own layout — no bespoke format, nothing to translate on
read — for example `data/bar/{instrument_id}/{start}_{end}.parquet`.
_Avoid_: corpus, Nautilus Catalog, Historical Store, bespoke store, ticker cache, provider cache

**InstrumentId**:
The native Nautilus instrument identity. It is the identity used in the catalog,
RD configs, Execution Bundles, candidate evidence, and live cache warmup.
_Avoid_: ticker, symbol, FIGI, InstrumentRef, provider locator

**DataProvider Port**:
The generic Nautilus market-data boundary that can satisfy missing catalog
windows and persist them. IBKR is one adapter behind this port, not the
architecture.
_Avoid_: IBKR dependency, provider-specific core API, custom fetch seam

**Raw Bars**:
OHLCV bars stored exactly as Nautilus `Bar` data for one native `InstrumentId`.
Raw bars are the r8b.1 walking skeleton. Currency conversion and split/dividend
handling are later slices.
_Avoid_: adjusted series, converted bars, continuous future

**Roll-Transition Table**:
The explicit list of roll seams — transition instant, the two legs by native
`InstrumentId`, and each leg's seam Close — that aegis-data derives as a pure
function over catalog legs (`continuous_future.py`). Handed to Nautilus via
`request_bars`/`subscribe_bars` `params`; the engine materialises the back-adjusted
continuous series on demand (Path A) under an explicitly supplied adjustment mode
(`BACKWARD_RATIO` or `BACKWARD_SPREAD`) — research supplies the mode it records as
Run evidence, live supplies the locked bundle contract's mode — and it is never
persisted. Golden tests pin the engine's output byte-for-byte for both backward
modes (root ADR-0009).
_Avoid_: implicit mode defaults on the shared path, bespoke back-adjust, persisted continuous series

**ContinuousContractModel**:
The stateful owner of one bare continuous-futures root's adjusted frame, front
leg, offset-0 append, roll re-materialisation, and last re-basing. Research and
live both drive this aegis-data object; live validates its synthetic continuous
`InstrumentId` against the declaration and never resolves a competing identity.
_Avoid_: trader-owned continuous feed, live identity resolver, duplicate front picker

**Coverage Gap**:
A requested Catalog interval nothing has answered for after any allowed lazy
fill. A Coverage Gap is a fail-loud condition; RD must not silently accept a
truncated series.

What holds the answer differs by record kind, and the reason is the vendor's,
not ours. Raw Bars answer from their own payload-file extents: every write
records the window it answered for, so the extents say what was *checked*, and
they are the same extents the Nautilus data engine reads when deciding whether
to fetch — one answer, no second opinion to keep in step. Distributions and
Custom Data answer from the dedicated coverage dataset, because Nautilus can
only record an empty window by extending an adjacent file's name: on a sparse
dataset with no neighbour there is nothing to extend, and "asked, and there was
nothing" is their ordinary answer rather than an edge case.
_Avoid_: partial success, best effort, sparse read

**Warm Then Sweep**:
The concurrency rule for research. A single writer populates the Catalog first
(live capture-forward, lazy fill, or backfill), then many reader processes run
against it once warm and immutable. A live session capturing forward is the
single writer for its whole lifetime, so research sweeps must not run against
that Catalog until the live session stops writing.
_Avoid_: shared catalog object across threads, concurrent writer swarm

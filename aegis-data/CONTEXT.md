# Aegis Data

Shared market-data context for Aegis RD and Aegis Trader. It owns the durable
Nautilus-native corpus and the port-backed read/fill behavior used by both
research and live.

## Language

**Nautilus Catalog**:
The durable `ParquetDataCatalog` rooted under the `aegis-data` OS data directory
(`AEGIS_DATA_DIR` override, then `catalog/`). It stores Nautilus-native data under
Nautilus' own layout, for example `data/bar/{instrument_id}/{start}_{end}.parquet`.
_Avoid_: Historical Store, bespoke store, ticker cache, provider cache

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
A requested catalog interval that `get_missing_intervals_for_request` says is
not covered after any allowed lazy fill. A coverage gap is a fail-loud condition;
RD must not silently accept a truncated series.
_Avoid_: partial success, best effort, sparse read

**Warm Then Sweep**:
The concurrency rule for research. A single writer populates the catalog first
(live capture-forward, lazy fill, or backfill), then many reader processes run
against the warm immutable parquet corpus.
_Avoid_: shared catalog object across threads, concurrent writer swarm

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

**Answered Interval**:
The exact time window for which a data source has completed an answer. The
answer may contain no records; absence is ordinary empty data.
_Avoid_: verified interval, coverage claim, checked window, verdict

**Roll-Transition Table**:
The explicit list of roll seams — transition instant, the two legs by native
`InstrumentId`, and each leg's seam Close — that aegis-data derives as a pure
function over catalog legs (`continuous_future.py`). Handed to Nautilus via
`request_bars` `params`; the engine materialises the back-adjusted continuous
series on demand (Path A) under an explicitly supplied adjustment mode
(`BACKWARD_RATIO` or `BACKWARD_SPREAD`). A `subscribe_bars` handoff is valid only
when its next transition is known before the boundary. Aegis learns a
volume-led live roll from the boundary bars themselves, so the live tail remains
in the shared `ContinuousContractModel`. Research supplies the mode it records
as Run evidence, live supplies the locked bundle contract's mode, and the series
is never persisted. Golden tests pin the engine's output byte-for-byte for both
backward modes (root ADR-0009).
_Avoid_: implicit mode defaults on the shared path, bespoke back-adjust, persisted continuous series

**ContinuousContractModel**:
The stateful owner of one bare continuous-futures root's adjusted frame, front
leg, offset-0 append, roll re-materialisation, and last re-basing. Research and
live both drive this aegis-data object; live validates its synthetic continuous
`InstrumentId` against the declaration and never resolves a competing identity.
_Avoid_: trader-owned continuous feed, live identity resolver, duplicate front picker

**Coverage Gap** (retired):
Absence in a requested Catalog interval is ordinary empty data, not an error.
Nautilus derives missing intervals from data-file extents and asks a configured
client when one is available; an un-warmed window with no client simply reads
empty. Every record kind uses those same extents. A sparse dataset that has
never held a record may therefore be requested again, which is cheaper and
simpler than maintaining a second dataset about the first.

Completeness is an operating discipline, not a read-time exception: **Warm Then
Sweep** warms the Catalog before a research run and keeps it immutable while
readers sweep it. Consumers that require a non-empty or sufficiently long
series judge that requirement in their own domain.
_Avoid_: coverage ledger, verified-empty marker, fail-loud absence

**Warm Then Sweep**:
The concurrency rule for research. A single writer populates the Catalog first
(live capture-forward, lazy fill, or backfill), then many reader processes run
against it once warm and immutable. A live session capturing forward is the
single writer for its whole lifetime, so research sweeps must not run against
that Catalog until the live session stops writing.
_Avoid_: shared catalog object across threads, concurrent writer swarm

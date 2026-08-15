# Nautilus-native audit: `aegis-data` and `aegis-runtime`

**Date:** 2026-08-15
**Baseline:** NautilusTrader 1.231.0
**Scope:** all production Python under `aegis-data/aegis_data` and
`aegis-runtime/aegis_runtime`

## Verdict

There is no second broad Nautilus implementation left in these two packages.
The important framework mechanics are already delegated: native data requests
split missing Catalog intervals and write responses back, custom records use
Nautilus Custom Data serialization, and historical continuous-future arithmetic
runs inside `DataEngine`.

The audit found two high-confidence cleanups and two bounded prototypes:

1. **Delete obsolete direct-write/correction APIs** left behind by the move to
   native request persistence. They have no production callers.
2. **Derive bar duration from `BarSpecification.get_interval_ns()`** and delete
   Aegis's duplicate nanosecond unit table.
3. **Prototype `NautilusConfig` for the Execution Bundle envelope**, but do not
   migrate yet: an exact-runtime experiment exposed wire-contract differences.
4. **Prototype native streaming only for live observed-event capture.** It is not
   a substitute for verified-empty Bar coverage.

Everything else examined is Aegis domain policy or an anti-corruption adapter,
not duplicated framework machinery.

## Method and evidence limits

Context7 resolved the official `/nautechsystems/nautilus_trader` corpus and was
used for API discovery across Custom Data, continuous futures, configuration,
indicators, portfolio/risk, currency conversion, and execution. Context7's
available corpus tracks `develop`, so every material compatibility claim below
was checked again against the installed **1.231.0** source in
`aegis-data/.venv/lib/python3.12/site-packages/nautilus_trader`; links point to
the corresponding official `v1.231.0` source or documentation.

The codebase graph audit used full generation `2026-08-15T12:59:01Z` at HEAD
`27c26895`. It covered 527 nodes/1,743 edges in `aegis-data/aegis_data` and 162
nodes/431 edges in `aegis-runtime/aegis_runtime`. Exact-path and bounded-scope
coverage checks found no source parse/skipped gaps; only `__pycache__`
directories were excluded. Every `.py` definition/import was also swept from
source, and candidate callers were checked with source search. A clean graph
coverage result is best-effort evidence, not proof of semantic completeness.

## Ranked findings

| Rank | Area | Decision |
|---|---|---|
| Strong simplification | Obsolete direct writers | Delete production `Catalog.store_definitions`, `write_distribution_data`, and `custom_data.correct`; retain test-only fixture helpers outside production |
| Strong, small simplification | Bar cadence | Replace `_UNIT_NS` with native `BarSpecification.get_interval_ns()` |
| Prototype first | Execution Bundle serialization | Test a `NautilusConfig`/msgspec envelope against the complete v5 wire contract |
| Prototype first | Live observed-event capture | Test `StreamingConfig` only for non-empty event capture and canonical conversion |
| Keep Aegis-owned | Catalog facade and request runner | Thin integration around native gap/request/write behavior |
| Keep Aegis-owned | Custom Data registry/projections | Domain mapping from records to Aegis Arrays |
| Keep Aegis-owned | Continuous roll discovery/live handoff | Nautilus requires caller-supplied transitions |
| Keep Aegis-owned | IBKR historical adapter | Fills missing upstream adjusted-history/failure APIs while reusing the vendor client |
| Keep Aegis-owned | Indicator execution | Locked vectorized Components are not native streaming Indicators |
| Keep Aegis-owned | Exposure/risk | Proposed-weight constraints differ from Nautilus order and position risk |
| Keep Aegis-owned | Currency conversion | Historical aligned Array conversion differs from current-cache exchange rates |
| Keep Aegis-owned | Rebasing and roll sensitivity | Carries Aegis state and validates strategies; native adjustment only transforms Bars |
| Keep Aegis-owned | Execution Bundle semantics | A versioned research-to-live artifact, not an order/execution-engine substitute |

## Strong simplifications

### 1. Remove obsolete direct-write and correction surfaces

Three production APIs no longer participate in production flows:

- [`Catalog.store_definitions`](../../aegis-data/aegis_data/storage.py#L284)
  writes definitions directly. Native `RequestInstrument(update_catalog=True)`
  now owns production definition persistence. Source and graph caller checks
  found only tests/fixtures using this method.
- [`write_distribution_data`](../../aegis-data/aegis_data/distributions.py#L196)
  implements its own per-instrument frontier and direct Catalog replacement.
  Production distribution derivation now enters through
  [`_DerivedDistributionProvider`](../../aegis-data/aegis_data/_distribution_verification.py#L68)
  and native `RequestData(update_catalog=True)`. Its remaining callers are test
  setup only.
- [`custom_data.correct`](../../aegis-data/aegis_data/custom_data.py#L371)
  performs a bounded direct replacement and compaction. It has one test caller
  and no production caller.

Nautilus 1.231.0's `DataEngine` asks the Catalog for missing intervals, splits a
date-range request, queries warm data, sends only gaps to the client, and writes
responses carrying `update_catalog`; see the versioned
[`_handle_date_range_request`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L2073-L2146)
and [`_update_catalog`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L3201-L3232).

Recommendation: move any useful fixture seeding into `aegis_data.testing` (or
test support packages) and delete these three production entry points. This
shrinks the public persistence vocabulary and prevents new code from bypassing
the native request lifecycle. `Catalog.replace` itself remains necessary for
live verified capture and explicit storage administration.

### 2. Use the native BarSpecification duration

[`bar_type.py`](../../aegis-data/aegis_data/bar_type.py#L32) duplicates the
SECOND/MINUTE/HOUR/DAY/WEEK-to-nanoseconds table in `_UNIT_NS`, then
[`timeframe_to_ns`](../../aegis-data/aegis_data/bar_type.py#L138) multiplies the
parsed step by that table.

Nautilus 1.231.0 already exposes
[`BarSpecification.get_interval_ns()` and `.timedelta`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/model/data.pyx#L677-L725),
including native validation of legal time-bar steps. Keep Aegis's valuable
pandas/VectorBT alias parser, but after parsing construct the native
`BarSpecification` and ask it for the interval. An exact-runtime check returned
the expected values for `1-DAY`, `1-WEEK`, and `15-MINUTE` and rejected an
invalid `2-DAY` specification.

This is a small deletion, but it places the duration rule next to the native bar
identity rule and removes duplicated vendor knowledge.

## Prototype-first candidates

### 3. Execution Bundle envelope on NautilusConfig/msgspec

[`bundle_loader.py`](../../aegis-runtime/aegis_runtime/execution/bundle_loader.py#L38)
uses a Pydantic envelope and `TypeAdapter`; [`bundle.py`](../../aegis-runtime/aegis_runtime/execution/bundle.py#L65)
adds Pydantic annotations to serialize Nautilus `InstrumentId` and adjustment
enums. Nautilus's own
[`NautilusConfig`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/config.py#L241-L339)
already provides frozen, unknown-field-forbidden msgspec configuration, JSON
parse/encode, schema generation, and native hooks for `InstrumentId` and enums.

An exact 1.231.0 experiment wrapped the current `DataContract`, `BundleManifest`,
and `LockedExecutionPlan` in a `NautilusConfig`. Instrument IDs—including mapping
keys—round-tripped correctly. It was **not** wire-equivalent: msgspec serialized
the derived `_exposure_limits` dataclass field and emitted
`adjustment_mode: null`, while v5 excludes the former and requires omission for
the latter. The current loader also deliberately enforces raw-field presence and
translates accumulated Pydantic errors into Aegis error types.

Recommendation: prototype a complete alternative envelope and compare exact
payload bytes/keys and every malformed-payload test. Adopt only if it deletes
the Pydantic wire annotations, adapter, and mirrored presence/error code without
recreating those rules elsewhere. Do **not** use
[`ImportableStrategyConfig`/`StrategyFactory`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/trading/config.py#L104-L151):
the bundle loads locked vectorized `module.run` Components, not Nautilus
`Strategy` subclasses.

### 4. Native streaming for observed live events only

Nautilus
[`StreamingConfig`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/persistence/config.py#L28-L77)
can persist bus traffic to Feather, and `ParquetDataCatalog` can later convert
stream files to canonical Parquet. That may replace the per-event direct write
inside [`custom_data.capture`](../../aegis-data/aegis_data/custom_data.py#L344)
if a spike proves identifier fidelity, restart behavior, deduplication, timely
availability to the running strategy, and safe Feather-to-Parquet conversion.

It cannot replace [`RawBars.record_verified`](../../aegis-data/aegis_data/raw_bars.py#L92):
streaming records events but has no representation for a completed subscribed
interval in which no event occurred. Aegis needs that negative fact to avoid
refetching a genuinely empty interval. Therefore native streaming is a bounded
custom-event capture experiment, not a Catalog coverage redesign.

## Keep Aegis-owned

### Catalog requests and Custom Data

[`run_catalog_request`](../../aegis-data/aegis_data/_catalog_request.py#L62)
constructs a short-lived `DataEngine`, registers the Catalog and one client, and
hides synchronous completion/failure handling. The gap calculation and write
algorithm are not in Aegis: the engine calls native
[`get_missing_intervals_for_request`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/persistence/catalog/parquet.py#L2344-L2388)
and native `write_data`. [`Catalog`](../../aegis-data/aegis_data/storage.py#L136)
is an information-hiding facade for typed keys, exact-nanosecond adjacency,
explicit correction, and coherent tests. Replacing it with direct
`ParquetDataCatalog` access would spread identifier/file-extent knowledge.

[`CustomDataWarmer`](../../aegis-data/aegis_data/custom_data.py#L185) creates a
native `RequestData(DataType(...), update_catalog=True)`; `ensure_arrays` merely
maps Aegis Array requirements to declared record kinds. `Distribution` and
`AdjustedClose` already use the native
[`customdataclass`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/model/custom.py#L31-L169)
serialization contract. The remaining registry, causal projection, value/
availability/age Arrays, and instrument applicability rules are Aegis domain
semantics.

### Continuous futures

Historical arithmetic is already native:
[`materialize_continuous_bars`](../../aegis-data/aegis_data/continuous_materialize.py#L73)
sends Aegis's transition table through `DataEngine`, whose native continuous
request path walks legs and applies cumulative adjustments. The official
[continuous-futures contract](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/concepts/continuous_futures.md)
requires callers to supply `continuous_future_transitions`; it does not discover
contracts, liquidity leadership, transition dates, or execution fronts.

Accordingly, [`ContinuousContractModel`](../../aegis-data/aegis_data/continuous_contract_model.py#L45)
correctly owns dynamic causal roll discovery and live leg control. A prior exact
subscription spike established that a transition learned from the boundary bars
cannot be supplied early enough for Nautilus to replay that same boundary. The
frozen-table handoff therefore does not simplify the current live lifecycle.

### IBKR historical compatibility

[`IbkrHistoricalProvider`](../../aegis-data/aegis_data/ibkr/historical.py#L136)
reuses Nautilus's `HistoricInteractiveBrokersClient` for definitions and Bars.
Its private reaches are isolated in `_HistoricSession` because 1.231.0 does not
surface teardown, does not pass `raise_on_error` through the public Bar request,
and cannot request IBKR `ADJUSTED_LAST` through its public historical Bar API.
This is fragile upstream compatibility code, but deleting it would require
reimplementing more of IBKR, not less. Prefer upstream Nautilus APIs when they
arrive; keep the adapter on 1.231.0.

### Indicators and MarketDataBundle

Nautilus Indicators are incremental state machines registered on an Actor and
automatically updated from Bars/ticks; the official pattern is
[`register_indicator_for_bars`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/actor.pyx#L847-L902).
[`ExecutionBundle._compute_indicators`](../../aegis-runtime/aegis_runtime/execution/bundle.py#L509)
instead executes the same locked vectorized Component modules used by research,
over complete aligned Array windows and candidate parameter shapes.

Replacing these Components with native streaming Indicators would create a
second research/live implementation or change the bundle contract. Likewise,
[`MarketDataBundle`](../../aegis-runtime/aegis_runtime/domain/market_data.py#L12)
is an aligned DataFrame value used by vectorized strategy code; it is not a
replacement for Nautilus's event Cache.

### Exposure and risk

[`validate_exposure`](../../aegis-runtime/aegis_runtime/domain/exposure_validation.py#L94)
checks proposed signed target-weight frames for direction, gross, and net limits
before orders exist. Nautilus 1.231.0's
[`RiskEngineConfig`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/risk/config.py#L24-L55)
offers command rate limits and maximum notional **per order**; Portfolio
[`net_exposures`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/portfolio/portfolio.pyx#L1029-L1141)
queries actual open positions. Neither validates a candidate weight matrix.
Keep Aegis's pre-decision gate and continue letting Nautilus risk/execution
engines validate and route the resulting orders downstream.

### Currency conversion

[`CurrencyConversion`](../../aegis-runtime/aegis_runtime/domain/currency.py#L75)
converts complete historical Array panels, aligns rates to every strategy row,
classifies which Arrays are denominated, and preserves research/live parity.
Nautilus [`Cache.get_xrate`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/cache/cache.pyx#L3742-L3832)
calculates a current scalar rate from the latest quote/BID-ASK bars; Portfolio
conversion acts on actual Money/exposure state. It cannot replace a historical
aligned conversion window. Calling the native scalar algorithm once per row
would add Cache/event reconstruction while replacing a direct/inverse vectorized
operation.

[`currency_units.py`](../../aegis-runtime/aegis_runtime/domain/currency_units.py#L1)
must also remain: Nautilus `Currency` has no major/minor-unit relationship for
codes such as `GBp`.

### Rebasing, roll sensitivity, and execution bundle behavior

Nautilus's continuous engine adjusts Bar history. It does not expose an object
that rebases Aegis-held state such as a ledger's pre-roll close. Therefore
[`rebasing.py`](../../aegis-runtime/aegis_runtime/domain/rebasing.py#L1) is a
necessary state-carry algebra, and
[`roll_sensitivity.py`](../../aegis-runtime/aegis_runtime/execution/roll_sensitivity.py#L60)
is an Aegis metamorphic validation of strategy invariance—not duplicate price
stitching.

The Execution Bundle records a locked research result, Array contract, component
hashes, drift bands, missing-index behavior, and roll mode. Nautilus's execution
engine owns commands/order state after submission; its
[`Strategy.submit_order`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/trading/strategy.pyx#L1290-L1365)
does not replace this research-to-live artifact. `DriftBand`, component loading,
roll-sensitivity probing, and bundle validation remain Aegis policy.

## Rejected candidates

- **Delete `Catalog` and call `ParquetDataCatalog` everywhere:** rejected;
  exposes serialized identifiers, file extents, adjacency, and correction rules
  to every caller.
- **Replace CustomDataWarmer/ensure_arrays with hand-issued catalog calls:**
  rejected; the current implementation already delegates to native requests.
- **Use BacktestDataConfig/BacktestNode here:** already evaluated elsewhere; the
  native Bar round-trip was removed, while wholesale node migration could not
  preserve Aegis simulation-module composition on 1.231.0.
- **Native continuous subscription for dynamic live rolls:** rejected by the
  causal boundary test; retain native historical adjustment only.
- **Native Indicators for locked vectorized Components:** rejected; changes the
  research/live computation model.
- **Portfolio.net_exposures as the weight gate:** rejected; it observes actual
  positions after execution rather than validating proposed weights.
- **Cache.get_xrate for Array conversion:** rejected; current scalar cache state
  is not a historical aligned panel.
- **RiskEngine as Execution Bundle validation:** rejected; it owns order-command
  risk, not the versioned research artifact.

## Recommended sequence

1. Delete the three obsolete production direct-write/correction APIs and migrate
   test fixtures to test support.
2. Replace `_UNIT_NS` with native `BarSpecification.get_interval_ns()`.
3. If further runtime simplification is desired, prototype the exact v5 bundle
   wire on `NautilusConfig`; implement only on a net deletion.
4. Treat native streaming capture as optional and lower priority. It must not
   weaken verified-empty coverage or immediate live availability.

# Nautilus-native delegation audit

**Date:** 2026-08-15
**Status:** Completed audit with implementation follow-up

**Implementation follow-up:** The strong candidates, native instrument seeding,
native-Bar backtest input, and native Distribution request lifecycle were
implemented later the same day. The remaining findings retain their
investigate/keep classifications.

## Conclusion

Aegis is already delegating the most consequential framework work to NautilusTrader: catalog-backed custom-data requests, historical continuous-future segment stitching and adjustment, event-driven simulation, fee/fill extension points, and performance-statistic calculation. The audit found two strong opportunities to become more Nautilus-native, plus several worthwhile investigation spikes. It did **not** find a second broad coverage system hidden behind `CustomDataWarmer` or `ensure_arrays`.

The clearest changes are:

1. Replace Aegis's manual `QuoteTick` construction with Nautilus's `QuoteTickDataWrangler`.
2. Build the complete public `TradingNodeConfig` before constructing `TradingNode`, instead of mutating `node._config` afterward.

The other apparent overlaps have material Aegis semantics—verified empty time, deterministic derived distributions, dynamic roll policy, cross-venue FX conversion, or IB-specific compatibility work—and should not be deleted without a focused equivalence prototype.

## Version and method

This audit uses NautilusTrader **1.231.0** as its API/source baseline. That is the version resolved by [`aegis-data/uv.lock`](../../aegis-data/uv.lock#L190), [`aegis-runtime/uv.lock`](../../aegis-runtime/uv.lock#L421), and [`aegis-rd/uv.lock`](../../aegis-rd/uv.lock#L1202). [`aegis-trader/uv.lock`](../../aegis-trader/uv.lock#L385) still resolves **1.229.0**. The trader lock should be synchronized before adopting behavior verified only against 1.231.0.

Evidence came from:

- the production Python scopes `aegis-data/aegis_data`, `aegis-trader/aegis_trader`, `aegis-runtime/aegis_runtime`, and `aegis-rd/research/aegis_research`;
- the codebase knowledge graph at commit `924921e8`, full-index generation `2026-08-14T15:25:08Z`, followed by exact-path and bounded-scope coverage checks;
- Context7's official `nautechsystems/nautilus_trader` documentation corpus;
- NautilusTrader's official, version-tagged documentation and source.

The graph recorded no source gaps in the cited production files. The only bounded-scope exclusions were `__pycache__` directories. Lockfiles are not graph-tracked, so their versions were verified directly from source. As always, a clean graph coverage signal is best-effort, not proof of semantic completeness.

## Ranked findings

| Rank | Area | Recommendation |
|---|---|---|
| **Strong candidate** | Live-node configuration | Compose public config before node construction; stop mutating `_config` |
| **Strong candidate** | FX quote construction | Use native `QuoteTickDataWrangler` |
| **Already native** | Historical continuous-future stitching | Keep supplying Aegis's transition table to Nautilus's request machinery |
| **Investigate** | IB instrument seeding | Test native request-to-catalog persistence after resolving metadata serialization |
| **Implemented** | Distribution materialization | Native `RequestData(update_catalog=True)` owns missing intervals and Catalog write-back |
| **Prototype only** | Request joining and `BacktestNode` | Evaluate newer/native orchestration; do not make it an implementation dependency yet |
| **Investigate** | Backtest data loading | Separate native engine input from Aegis's research/domain frame view |
| **Investigate** | Live capture | Test whether native streaming can preserve Aegis's canonical and verified-silence semantics |
| **Investigate** | Live continuous futures | Let native subscriptions take over only after Aegis freezes the transition table |
| **Keep Aegis-owned** | Custom-data warming | Already a thin facade over native data requests and catalog gap handling |
| **Keep Aegis-owned** | Continuous roll policy | Nautilus explicitly leaves transition discovery to the caller |
| **Keep Aegis-owned** | Multi-currency NAV/performance | Native analyzer does not calculate multi-currency portfolio returns |
| **Keep Aegis-owned** | IB historical compatibility | Already delegates ordinary requests to Nautilus's IB client |
| **Keep Aegis-owned** | Financing, dividends, and broker costs | Domain policies implemented through Nautilus extension points |

## Strong candidates

### 1. Compose `TradingNodeConfig` through public APIs

[`build_live_node`](../../aegis-trader/aegis_trader/trader/node.py#L141) constructs a `TradingNode` and then calls two helpers. [`attach_live_clients`](../../aegis-data/aegis_data/ibkr/live.py#L40) and [`add_live_custom_data`](../../aegis-trader/aegis_trader/trader/live_custom_data.py#L110) both read and replace the private `node._config` before `node.build()`.

Nautilus's public composition model puts `data_clients` and `exec_clients` on `TradingNodeConfig`; client factories are then registered before `build()`. See [`TradingNodeConfig`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/live/config.py#L284-L355) and the [official Interactive Brokers integration guide](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/integrations/ib.md).

Refactor the current helpers to return client-config contributions—or one complete provider-neutral config value—then instantiate `TradingNode` once from the finished config. Factory registration can remain through the node's public API. The existing Aegis mapping from book/connection settings to Nautilus config is useful anti-corruption logic; the problem is only the post-construction private mutation.

**Why strong:** `_config` is an implementation detail, while Nautilus exposes the needed configuration surface directly. This removes framework coupling without removing domain behavior.

### 2. Use `QuoteTickDataWrangler` for synthetic FX quotes

[`wrangle_fx_quotes`](../../aegis-trader/aegis_trader/data/backtest_data.py#L84) loops over a pandas series, applies instrument price and size precision, converts each timestamp, and constructs `QuoteTick` objects manually. The production backtest path then adds these ticks to the engine.

Nautilus 1.231.0 already provides `QuoteTickDataWrangler.process`, which accepts a timestamp-indexed DataFrame with `bid_price` and `ask_price` columns, defaults missing sizes, and emits precision-correct `QuoteTick` objects for a supplied instrument. See the [version-tagged wrangler implementation](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/persistence/wranglers.pyx#L287-L356).

The Aegis input is a mid/mark series rather than a real bid/ask feed, but that does not require a custom event constructor: pass the series as both `bid_price` and `ask_price`. Preserve the current default size explicitly if its value matters. Before deletion, add a parity test for timestamp selection, zero/NaN handling, and instrument precision.

**Why strong:** this is direct duplication of a stable public persistence adapter, with no Aegis-only state model.

## Investigate before changing

### 3. Route derived Distribution filling through the DataEngine — implemented

The Context7/API review and an executable spike against the installed 1.231.0
runtime compared cold records, a never-populated empty dataset, an empty tail
beside stored data, warm repetition, and failure propagation. Native
`RequestData(update_catalog=True)` matched `Catalog.fill`'s file-extent and
repeat-request behavior in every storage case.

Distribution derivation is now a local provider behind the existing Custom Data
client. Aegis still owns the deterministic calculation from stored trade closes
and `AdjustedClose`; Nautilus's `DataEngine` owns missing-interval discovery,
request grouping, and Catalog write-back. Existing `GapFillProviderError` values
pass through the nested request unchanged, avoiding a duplicate provider-error
layer. The now-redundant `Catalog.fill` algorithm was deleted.

This is reuse rather than a new lifecycle: provider-backed custom data already
constructs the request engine and client binding. Adding `Distribution` to that
path removes a second gap/write algorithm while retaining the Catalog port as
the single public verification seam.

### 4. Avoid the catalog Bar → DataFrame → Bar backtest round trip

[`CatalogBacktestDataSource.load`](../../aegis-trader/aegis_trader/backtest.py#L141) obtains OHLCV frames from catalog-backed native bars. Later, [`_add_instruments_and_bars`](../../aegis-trader/aegis_trader/backtest.py#L579) converts those frames back into Nautilus `Bar` objects with `BarDataWrangler` and adds them to `BacktestEngine`. [`run_book_backtest`](../../aegis-trader/aegis_trader/backtest.py#L187) also coordinates instruments, bars, quotes, custom events, and simulation modules manually.

Nautilus 1.231.0's `BacktestDataConfig` can query `Bar` or custom data directly from a `ParquetDataCatalog`, including explicit `bar_types` or instrument/bar-spec combinations. `BacktestNode` then loads instruments and data and supports one-shot or streaming execution. See [`BacktestDataConfig`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/backtest/config.py#L195-L289) and [`BacktestNode`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/backtest/node.py).

The clean seam is likely two views:

- native catalog records/configs for engine input;
- Aegis DataFrames only where vectorized research, validation, or domain array assembly needs them.

The spike rejected a wholesale `BacktestNode` migration on Nautilus 1.231.0: native catalog loading was lossless and runtime strategies could attach after `build()`, but the config surface rejected Aegis's already-constructed financing/dividend simulation modules. The implemented narrower design keeps the existing runner and carries the native Bars already held by `RawBarWindow` through `CatalogWindow` into `BacktestEngine`. OHLCV and sided quote frames remain projections for validation, domain arrays, marking, and synthetic FX quotes. This removes the conversion and a second quote-frame catalog read without weakening preflight or changing simulation composition.

### 5. Let native instrument requests update the catalog—if IB metadata is safe

[`seed_instrument_definitions`](../../aegis-data/aegis_data/ibkr/historical.py#L819) checks the catalog, calls `IbkrHistoricalProvider.request_instruments`, sanitizes each instrument's `info`, and writes definitions explicitly.

Nautilus can issue an instrument download with catalog update enabled; its DataEngine handles instrument responses and catalog persistence. See [`BacktestNode.download_data`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/backtest/node.py#L300-L352) and the instrument update path in [`DataEngine`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L2568-L2604).

The blocker is not orchestration but data compatibility: Aegis recursively removes IB `info` values that are not msgspec-encodable before persistence. A native request-to-catalog flow is only preferable if 1.231.0 can persist the returned IB instruments without that sanitizer and preserve Aegis's MIC identity rules. Test this with representative equity, future, option, and FX instruments. If it fails, keep the Aegis adapter and consider an upstream Nautilus issue rather than bypassing serialization locally in more places.

### 6. Evaluate native streaming for live capture, but preserve verified silence

[`BarCapture`](../../aegis-trader/aegis_trader/trader/bar_capture.py#L18) buffers observed bars, verifies a completed interval using the session clock, and calls [`RawBars.record_verified`](../../aegis-data/aegis_data/raw_bars.py#L92). Importantly, `record_verified` persists interval extent even when the interval contains no bars. [`_CustomDataCaptureActor`](../../aegis-trader/aegis_trader/trader/live_custom_data.py#L40) similarly subscribes to custom data and writes observed records into the canonical catalog.

Nautilus's [`StreamingConfig`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/persistence/config.py#L28-L77) can attach a streaming writer to live or backtest nodes and persist bus traffic. That may be usable for observed custom-data capture.

It is not currently a drop-in replacement for `BarCapture`. The native writer targets a streaming/Feather layout under environment and instance directories, while Aegis requires immediate canonical catalog availability plus a negative fact: a subscribed, completed interval with no event is still verified coverage. A prototype must prove identifier fidelity, deduplication, consolidation into the canonical catalog, restart behavior, and explicit empty-interval semantics. Until then, keep `BarCapture`; it owns an invariant the generic stream writer does not express.

### 7. Delegate live continuous output only after Aegis decides the roll

Historical continuous-bar production is already native. [`ContinuousFuture.request_params`](../../aegis-data/aegis_data/continuous_future.py#L79) supplies a transition table and adjustment mode; [`materialize_continuous_bars`](../../aegis-data/aegis_data/continuous_materialize.py#L71) sends a native bar request through `DataEngine`.

Nautilus 1.231.0 also supports continuous-future subscriptions: the engine walks contract segments and maintains cumulative adjustments. But the official design explicitly requires the caller to provide the transition table; Nautilus does not discover rolls, choose contracts, or infer transition prices. See the [official continuous-futures design](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/concepts/continuous_futures.md).

[`RollDesk`](../../aegis-trader/aegis_trader/trader/roll_desk.py#L37) currently subscribes candidate legs, evaluates Aegis's live liquidity policy, updates the execution front, and rematerializes continuous history. Investigate whether a **frozen** transition table can be handed to a native continuous subscription so Nautilus owns adjusted output from that point forward. Do not push dynamic roll discovery or execution-front selection into Nautilus; those remain Aegis domain policy.

### 8. Minor: derive timeframe duration from the native bar specification

[`bar_type.py`](../../aegis-data/aegis_data/bar_type.py#L1) is a useful anti-corruption adapter from pandas/VectorBT spelling to Nautilus bar specifications. Keep that mapping. The small `timeframe_to_ns` duration table is duplicated knowledge, though: after parsing, duration can potentially come from the native `BarSpecification.timedelta`. This is low-value cleanup and should only proceed if all supported aliases retain exact semantics.

## Keep Aegis-owned

### Custom-data warming is already Nautilus-native integration

[`CustomDataWarmer`](../../aegis-data/aegis_data/custom_data.py#L185) constructs a native `DataEngine` request for registered `DataType`s with `update_catalog=True`. [`ensure_arrays`](../../aegis-data/aegis_data/custom_data.py#L254) only maps declared Aegis array requirements to registered types/providers and invokes that flow. This is integration orchestration, not another coverage ledger or a hand-rolled custom-data transport. Keep it unless the caller-facing facade itself stops earning its place.

The derived `AdjustedClose`/`Distribution` model is also appropriately expressed as Nautilus custom data. The open question is only whether the remaining distribution fill operation should run through the same native request path, covered above.

### Continuous roll discovery and execution policy belong to Aegis

Aegis's continuous-future model chooses candidate contracts and transition dates from chain and liquidity rules. Nautilus's documented contract begins **after** those choices are supplied. Aegis should continue to own roll policy while delegating segment walking and price adjustment, which is what the historical path already does.

### Multi-currency book equity and return preparation fill a native gap

[`NautilusBookState`](../../aegis-trader/aegis_trader/portfolio/book_state.py#L58) reads native portfolio/cache state but performs venue-agnostic FX conversion to the book currency. [`BookEquityRecorder`](../../aegis-trader/aegis_trader/portfolio/performance.py#L49) records that base-currency NAV, and [`return_stats`](../../aegis-trader/aegis_trader/portfolio/performance.py#L111) feeds the return series into Nautilus's `PortfolioAnalyzer` statistics.

This division is appropriate in 1.231.0. Nautilus's analyzer explicitly does not calculate portfolio returns for multi-currency accounts; it returns no portfolio series and may fall back to position returns. See [`PortfolioAnalyzer._calculate_portfolio_returns`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/analysis/analyzer.py#L816-L869). Native portfolio equity is exposed per currency rather than as an arbitrary target-currency total; see [`Portfolio.equity`](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/portfolio/portfolio.pyx#L1173-L1268).

Keep Aegis's conversion and sampling. It already defers statistical calculation to Nautilus instead of reimplementing the whole analyzer.

### IB historical code is an anti-corruption adapter, not a replacement client

[`IbkrHistoricalProvider`](../../aegis-data/aegis_data/ibkr/historical.py#L134) delegates ordinary instrument and bar history to Nautilus's `HistoricInteractiveBrokersClient`. [`_HistoricSession`](../../aegis-data/aegis_data/ibkr/historical.py#L590) reaches into narrower APIs for lifecycle/error propagation and the IB-specific `ADJUSTED_LAST` request that Nautilus's public historical surface does not fully expose.

Keep the wrapper today. Potential upstream requests—public teardown, adjusted-history support, or consistent `raise_on_error` propagation—could shrink it later. Reimplementing the full IB client in Aegis would move in the wrong direction; the current code does not do that.

### Financing, distributions, and broker costs correctly use extension points

[`FinancingModule`](../../aegis-trader/aegis_trader/trader/financing.py#L32) and [`DividendModule`](../../aegis-trader/aegis_trader/trader/dividends.py#L28) implement Aegis accounting policies through Nautilus `SimulationModule` behavior. [`IbkrEquityFeeModel`](../../aegis-trader/aegis_trader/trader/costs.py#L49) implements broker-specific pricing through Nautilus's `FeeModel` extension point. These are policies the framework is designed to receive, not framework mechanics Aegis has copied.

### Research simulation is intentionally a different engine

The production code under `aegis-rd/research/aegis_research` is VectorBT-oriented research and optimization infrastructure. No bounded finding showed it rebuilding a Nautilus subsystem that should instead be delegated. Shared market-data and catalog concerns belong at the `aegis-data`/`aegis-trader` boundaries, not by forcing Nautilus runtime objects into vectorized research code.

## Suggested ticket sequence

Do not create all investigation tickets as implementation work. The following order keeps the high-confidence deletions ahead of speculative architecture changes:

1. **Use `QuoteTickDataWrangler` for backtest FX quote construction.** Implementation ticket; include behavioral parity tests.
2. **Compose live data/execution clients before `TradingNode` construction.** Implementation ticket; acceptance criterion is zero access to `TradingNode._config`.
3. **Implemented: native request lifecycle for deterministic Distribution materialization.** The exact-version spike preserved extent and empty-interval behavior; `Catalog.fill` was deleted.
4. **Implemented: feed the catalog window's native Bars directly to the backtest engine.** DataFrame projections remain only for validation and domain consumers; `BacktestNode` orchestration was rejected for 1.231.0.
5. **Validate native IB instrument request-to-catalog persistence.** Compatibility ticket; cover msgspec metadata and MIC identity before deleting the seeding path.
6. **Spike: native streaming equivalence for observed custom data and bars.** Decision ticket; verified-empty time is a hard acceptance criterion for bars.
7. **Spike: native continuous subscription after transition freeze.** Low-priority decision ticket; Aegis remains the owner of roll discovery and execution-front policy.

The first two are strong simplifications. The remaining items should produce evidence and a keep/delete decision, not presume that “more native” is automatically a shallower design.

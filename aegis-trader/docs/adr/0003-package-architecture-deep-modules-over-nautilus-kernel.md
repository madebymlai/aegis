# Aegis Trader package architecture: deep modules over the Nautilus kernel

Status: accepted, amended 2026-06-20 (aegis-rd-8pt)

Aegis Trader is a NautilusTrader overlay (ADR-0001). Nautilus already provides the live/backtest kernel: `MessageBus`, `Cache`, `DataEngine`, `ExecutionEngine`, `RiskEngine`, `Portfolio`, and one `Strategy` event loop that runs across backtest, paper, and live. The Trader architecture therefore wraps Nautilus only where the wrapper hides Trader-specific depth. It does **not** create parallel execution or observability ports.

## Module map

| Concern | Package/module | Boundary | Depth — what the module hides |
|---|---|---|---|
| Market data | `data/market_data.py` | `MarketDataPort` + `NautilusMarketData` in one module | Cache-backed native bar windows, per-period freshness, instrument sizing, native quantity construction, and FX marks. |
| Book state | `portfolio/book_state.py` | `BookStatePort` + `NautilusBookState` in one module | NAV/cash aggregation, cache health, and base-currency realized weights from Nautilus portfolio/cache reads. |
| Bundle loading | `bundles/` | `BundleRegistryPort` with stub and entry-point implementations | Installed Execution Bundle discovery, wheel-label lookup, and cap provenance against the bundle's locked plan. This is the only remaining justified port/adapter file split because it has multiple implementations. |
| Rebalance orchestration | `trader/pipeline.py` | `RebalancePipeline` value-object API | Startup gates, pipeline-owned `InstrumentRef`↔`InstrumentId` identity, Cache-backed market-data reads through ports, Execution Bundle calls, netting/gating, sizing, freshness filtering, and the `SleeveLedger`. Imports no Strategy or Nautilus event-loop types. |
| Nautilus adapter | `trader/strategy.py`, `trader/modes.py` | Native Nautilus `Strategy` and node/client configs | Lifecycle, bar-driven period rollover, futures roll refresh, FX quote mirroring into Cache marks, translating `OrderIntent`s into Nautilus orders, RiskEngine config, and structured `self.log` records. |

## Dependency rule

```
domain/*            -> pure value objects and algorithms, no Nautilus
bundles/*           -> bundle registry/provenance, no Strategy lifecycle
trader/pipeline.py  -> domain + bundle/data/portfolio ports, no Strategy effects
trader/strategy.py  -> Nautilus lifecycle and I/O effects over the pipeline
trader/modes.py     -> Nautilus environment/client wiring
```

`data/market_data.py` and `portfolio/book_state.py` may import Nautilus facade types because the Trader is a Nautilus overlay and these ports intentionally hide Nautilus read trains. The Nautilus-free boundary that matters is `domain/*` plus the value-object surface returned by `RebalancePipeline`.

## Realized rebalance-pipeline shape

`RebalancePipeline` is the deep module ADR-0003 originally intended:

- `startup_check() -> StartupResult` runs cap-provenance and account-integrity gates. A failed gate returns a typed halt gate plus human reason; the Strategy logs it and idles before any order can be submitted.
- `initialize_identity(as_of)`, `refresh_resolution(as_of)`, and `resolve_contract_id_for_roll(...)` own `InstrumentRef`↔Nautilus `InstrumentId` identity behind one injected resolver. Live uses the provider-backed resolver; backtests and e2e tests inject `FixtureInstrumentResolver`.
- `rebalance_period(CompletedRebalancePeriod) -> RebalanceResult` reads completed-period windows and freshness through `MarketDataPort`, computes sleeve targets from Execution Bundles, builds the rebalance plan, sizes deltas, filters stale instruments, records the `SleeveLedger`, and returns `OrderIntent`s plus a `RebalanceSummary` carrying the real gate outcome.
- The owned `SleeveLedger` supplies realized covariance for the next rebalance and end-of-run evidence (realized book skew and per-sleeve P&L attribution).

`RebalanceStrategy` is the thin Nautilus adapter around that shape. It wires cache-backed ports and the resolver at `on_start`, logs `StartupResult` / `RebalanceSummary` / end-of-run evidence through native `self.log`, subscribes bars and FX reference quotes, keeps the bar-driven period rollover trigger, refreshes futures rolls, and submits returned orders through Nautilus's own order factory and `ExecutionEngine`.

## Explicit non-ports

- **No `ExecutionPort`.** Order submission goes through Nautilus's venue-agnostic order factory, `ExecutionEngine`, and `RiskEngine` from the Strategy. IBKR-specific behavior belongs in Nautilus client/provider configuration in `trader/modes.py` and the injected provider resolver, not in a Trader execution adapter.
- **No `ObservabilityPort`.** The shipped sink is Nautilus's native logger (`self.log`). A future subscriber-based backend should attach to Nautilus `MessageBus` (`publish_signal` / `publish_data`) rather than reintroducing a shallow Trader port.
- **No Cache wrapper.** Cache remains Nautilus's reconciled source of truth. Trader-owned state is limited to regenerable pipeline identity and the pure `SleeveLedger` observations.

## Directory layout

```
aegis_trader/
  bundles/                    # BundleRegistryPort + implementations, provenance
  data/market_data.py          # MarketDataPort + NautilusMarketData
  domain/                      # pure algorithms and value types
  portfolio/book_state.py      # BookStatePort + NautilusBookState
  trader/
    instrument_provider.py     # provider-loaded InstrumentRef -> InstrumentId helpers
    pipeline.py                # StartupResult/RebalanceResult orchestration
    strategy.py                # Nautilus Strategy adapter
    modes.py                   # backtest | paper | live wiring
```

## Consequences

- Misconfigured caps and unhealthy account state halt in the pipeline and are only reported by the Strategy.
- The Strategy holds no bar buffer, no externally-writable identity bimap, and no analytics ledger beyond the pipeline-owned `SleeveLedger` seam.
- Per-period orchestration and startup decisions are unit-testable without a Nautilus node; the e2e backtest suite remains the behavioral regression seam for netting, sizing, rolls, FX, gates, and attribution.
- Adding a second observability backend is a Nautilus `MessageBus` subscriber concern, not a new dependency of the domain or pipeline.

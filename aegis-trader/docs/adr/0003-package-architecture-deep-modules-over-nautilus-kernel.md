# Aegis Trader package architecture: deep modules over the Nautilus kernel

Status: accepted, amended 2026-06-20 (aegis-rd-8pt), 2026-06-23 (aegis-rd-r8b.8 — modes.py dissolves; IBKR config leaves the Trader; see amendment below)

Aegis Trader is a NautilusTrader overlay (ADR-0001). Nautilus already provides the live/backtest kernel: `MessageBus`, `Cache`, `DataEngine`, `ExecutionEngine`, `RiskEngine`, `Portfolio`, and one `Strategy` event loop that runs across backtest, paper, and live. The Trader architecture therefore wraps Nautilus only where the wrapper hides Trader-specific depth. It does **not** create parallel execution or observability ports.

## Module map

| Concern | Package/module | Boundary | Depth — what the module hides |
|---|---|---|---|
| Market data | `data/market_data.py` | `MarketDataPort` + `NautilusMarketData` in one module | Cache-backed native bar windows, per-period freshness, instrument sizing, native quantity construction, and FX marks. |
| Book state | `portfolio/book_state.py` | `BookStatePort` + `NautilusBookState` in one module | NAV/cash aggregation, cache health, and base-currency realized weights from Nautilus portfolio/cache reads. |
| Bundle loading | `bundles/` | `BundleRegistryPort` with stub and entry-point implementations | Installed Execution Bundle discovery and wheel-label lookup. This is the only remaining justified port/adapter file split because it has multiple implementations. |
| Rebalance orchestration | `trader/pipeline.py` | `RebalancePipeline` value-object API | Startup gates, Cache-backed market-data reads through ports, Execution Bundle calls, netting/gating, sizing, freshness filtering, and the `SleeveLedger`. Imports no Strategy or Nautilus event-loop types. |
| Nautilus adapter | `trader/strategy.py`, `trader/node.py` | Native Nautilus `Strategy`; broker-neutral `TradingNode`/backtest config + the live run/stop lifecycle | Lifecycle, bar-driven period rollover, futures roll refresh, FX quote mirroring into Cache marks, translating `OrderIntent`s into Nautilus orders, RiskEngine config, the `trader start`/`stop` daemon, and structured `self.log` records. IBKR client/connection config is **not** here — it lives in the one IBKR adapter (`aegis-data/ibkr.py`); `node.py` carries no broker vocabulary. |

## Dependency rule

```
domain/*            -> pure value objects and algorithms, no Nautilus
bundles/*           -> bundle registry and contract assembly, no Strategy lifecycle
trader/pipeline.py  -> domain + bundle/data/portfolio ports, no Strategy effects
trader/strategy.py  -> Nautilus lifecycle and I/O effects over the pipeline
trader/node.py      -> broker-neutral Nautilus node + live run/stop lifecycle; no IBKR SDK
                       import and no ibg_*/IDEALPRO vocabulary — reaches IBKR only through the
                       single aegis_data.ibkr.attach_live_clients seam (lazy ibapi behind it)
backtest.py         -> backtest engine + non-live RiskEngine config (was trader/modes.py)
```

`data/market_data.py` and `portfolio/book_state.py` may import Nautilus facade types because the Trader is a Nautilus overlay and these ports intentionally hide Nautilus read trains. The Nautilus-free boundary that matters is `domain/*` plus the value-object surface returned by `RebalancePipeline`.

## Realized rebalance-pipeline shape

`RebalancePipeline` is the deep module ADR-0003 originally intended:

- `startup_check() -> StartupResult` runs cap-provenance and account-integrity gates. A failed gate returns a typed halt gate plus human reason; the Strategy logs it and idles before any order can be submitted.
- Identity needs no pipeline resolver: each Execution Bundle declares its native Nautilus `InstrumentId`s, `union_native_instrument_ids` unions them across sleeves (`bundles/book_sleeves.py`), and IBKR's `InstrumentProvider.load_ids` resolves them at boot (root ADR-0007). The futures roll is driven by the Roll Desk over `aegis-data`'s `ContinuousContractModel` — live, keyed by `InstrumentId` — not by a pipeline resolution step.
- `rebalance_period(CompletedRebalancePeriod) -> RebalanceResult` reads completed-period windows and freshness through `MarketDataPort`, computes sleeve targets from Execution Bundles, builds the rebalance plan, sizes deltas, filters stale instruments, records the `SleeveLedger`, and returns `OrderIntent`s plus a `RebalanceSummary` carrying the real gate outcome.
- The owned `SleeveLedger` supplies realized covariance for the next rebalance and end-of-run evidence (realized book skew and per-sleeve P&L attribution).

`RebalanceStrategy` is the thin Nautilus adapter around that shape. It wires cache-backed ports and the resolver at `on_start`, logs `StartupResult` / `RebalanceSummary` / end-of-run evidence through native `self.log`, subscribes bars and FX reference quotes, keeps the bar-driven period rollover trigger, refreshes futures rolls, and submits returned orders through Nautilus's own order factory and `ExecutionEngine`.

## Explicit non-ports

- **No `ExecutionPort`.** Order submission goes through Nautilus's venue-agnostic order factory, `ExecutionEngine`, and `RiskEngine` from the Strategy. IBKR-specific behavior belongs in the single IBKR adapter (`aegis-data/ibkr.py`) — connection-config translation only, building Nautilus's *stock* `InteractiveBrokers{Data,Exec}ClientConfig` + registering the stock live factories — not in the Trader's `node.py` or a Trader execution adapter.
- **No `ObservabilityPort`.** The shipped sink is Nautilus's native logger (`self.log`). A future subscriber-based backend should attach to Nautilus `MessageBus` (`publish_signal` / `publish_data`) rather than reintroducing a shallow Trader port.
- **No Cache wrapper.** Cache remains Nautilus's reconciled source of truth. Trader-owned state is limited to Roll Desk orchestration and the pure `SleeveLedger` observations; the continuous series state lives in `aegis-data`'s `ContinuousContractModel`.

## Directory layout

```
aegis_trader/
  bundles/                    # BundleRegistryPort + implementations, provenance
  data/market_data.py          # MarketDataPort + NautilusMarketData
  domain/                      # pure algorithms and value types
  portfolio/book_state.py      # BookStatePort + NautilusBookState
  trader/
    pipeline.py                # StartupResult/RebalanceResult orchestration
    strategy.py                # Nautilus Strategy adapter
    node.py                    # broker-neutral live TradingNode + run/stop lifecycle (trader start/stop)
```

(Backtest engine/RiskEngine config lives in `aegis_trader/backtest.py`; the one
IBKR adapter is `aegis-data/aegis_data/ibkr.py`.)

## Consequences

- Misconfigured caps and unhealthy account state halt in the pipeline and are only reported by the Strategy.
- The Strategy holds no bar buffer, no externally-writable identity bimap, and no analytics ledger beyond the pipeline-owned `SleeveLedger` seam.
- Per-period orchestration and startup decisions are unit-testable without a Nautilus node; the e2e backtest suite remains the behavioral regression seam for netting, sizing, rolls, FX, gates, and attribution.
- Adding a second observability backend is a Nautilus `MessageBus` subscriber concern, not a new dependency of the domain or pipeline.

## Amendment — 2026-06-23 (aegis-rd-r8b.8): `modes.py` dissolves; IBKR config leaves the Trader

The original module map parked all "backtest | paper | live" wiring — including
hand-rolled IBKR client-config dicts — in `trader/modes.py`. Two problems: the
`backtest | paper | live` taxonomy conflated one genuinely different thing (the
offline engine) with a non-distinction (paper vs live is *only* which gateway
port you connect to — IBKR's own guidance: "transition from paper to live is
simply changing the port number"); and IBKR vocabulary leaked into the Trader's
node module, when the epic thesis (bd `aegis-rd-r8b`) is to **depend on the
Nautilus DataProvider port with IBKR as the first adapter using Nautilus's stock
code** — one IBKR seam, not several.

`modes.py` is therefore **dissolved**:

- **Backtest** engine + non-live `RiskEngine` config → `aegis_trader/backtest.py`
  (its only caller).
- **Live node** config (`Environment.LIVE`, `trader_id`, live `RiskEngine`,
  cache, logging, catalogs) + the run/stop lifecycle → broker-neutral
  `aegis_trader/trader/node.py`. It wires the broker through one call,
  `ibkr.attach_live_clients(node, connection, instrument_ids)`, and
  carries **no** `ibg_*`/`IDEALPRO` vocabulary.
- **IBKR** client-config building + factory registration + IB constants → the
  **single** IBKR adapter `aegis-data/aegis_data/ibkr.py` (renamed from
  `ibkr_provider.py` + extended; lazy `ibapi`). It builds Nautilus's *stock*
  `InteractiveBrokers{Data,Exec}ClientConfig` and registers the stock live
  factories — no custom adapter code. The same module already owns the historic
  fetch path, so research and live connect to IBKR through one seam (this
  branch's *live-research parity* mandate). It exposes a `dockerized_gateway`
  seam for the Dockerized daemon (bd `aegis-rd-r8b.6`).
- The mode-keyed `fill_time_in_force_for_mode` → two named values: backtest ⇒
  plain `MARKET` (`None`); live ⇒ `AT_THE_CLOSE`. The dead
  `fx_reference_instrument_ids` helper (constructed broker FX ids from
  currencies) is **deleted** — FX natives are declared in config (`data:
  exchange:`) and ride into the Trader inside `DataContract.instrument_ids`.

The **"No `ExecutionPort`" invariant is preserved**: orders still flow through
Nautilus's venue-agnostic factory from the Strategy; the IBKR adapter only
*translates connection config*, holding no execution policy (account identity is
injected via the Trader-owned **Broker Connection**, `IBConnectionSettings`).

The CLI now **owns the live `node.run()` lifecycle** (previously "the operator's
runtime step"): `aegis-trader trader start` builds the node, registers the IBKR
factories, adds the strategy, and runs it in the **foreground** with the
Nautilus-correct shutdown (`try / except KeyboardInterrupt / finally:
node.stop(); node.dispose()`); `trader stop` sends `SIGTERM` to a pidfile.
(POSIX SIGTERM is delivered; Windows only gets Ctrl-C/SIGINT — not a target
platform.) `IBConnectionSettings.from_env` drops the `mode` parameter and
**requires `IB_PORT`** (fail-closed — Nautilus defaults `ibg_port=None`, and the
port is the live/paper switch).

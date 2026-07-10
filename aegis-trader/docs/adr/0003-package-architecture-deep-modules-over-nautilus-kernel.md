# Aegis Trader package architecture: deep modules over the Nautilus kernel

Status: accepted, amended 2026-06-20 (aegis-rd-8pt), 2026-06-23 (aegis-rd-r8b.8 — modes.py dissolves; IBKR config leaves the Trader; see amendment below), 2026-07-10 (aegis-rd-57aa — deep Book assembly), 2026-07-10 (aegis-rd-qllq — rebalance planning is internal to RebalancePipeline; see amendment below)

Aegis Trader is a NautilusTrader overlay (ADR-0001). Nautilus already provides the live/backtest kernel: `MessageBus`, `Cache`, `DataEngine`, `ExecutionEngine`, `RiskEngine`, `Portfolio`, and one `Strategy` event loop that runs across backtest, paper, and live. The Trader architecture therefore wraps Nautilus only where the wrapper hides Trader-specific depth. It does **not** create parallel execution or observability ports.

## Module map

| Concern | Package/module | Boundary | Depth — what the module hides |
|---|---|---|---|
| Market data | `data/market_data.py` | `MarketDataPort` + `NautilusMarketData` in one module | Cache-backed native bar windows, per-period freshness, instrument sizing, native quantity construction, and FX marks. |
| Book state | `portfolio/book_state.py` | `BookStatePort` + `NautilusBookState` in one module | NAV/cash aggregation, cache health, and base-currency realized weights from Nautilus portfolio/cache reads. |
| Book assembly | `bundles/book.py` | `assemble_book(BookConfig, BundleRegistryPort) -> AssembledBook` | Sleeve resolution, deterministic loadable IDs, timeframe, warmup window, margin need, band ownership, and coherent continuous-root declarations. Structurally invalid Books fail before broker attachment. |
| Bundle registry | `bundles/port.py`, `bundles/registry.py`, `bundles/stub.py` | `BundleRegistryPort` with stub and entry-point implementations | Installed Execution Bundle discovery and wheel-label lookup. This is the only remaining justified port/adapter file split because it has multiple implementations. |
| Rebalance orchestration | `trader/pipeline.py` (+ private `trader/_rebalancer.py`) | `RebalancePipeline` value-object API | Account-integrity startup gate, Cache-backed market-data reads through ports, Execution Bundle calls, the whole ADR-0002 rebalance plan (allocate, net, clamp, band, remediate, cap-gate — implemented by the pipeline-private `_rebalancer` module), sizing, freshness filtering, and the `SleeveLedger`. Imports no Strategy or Nautilus event-loop types. |
| Nautilus adapter | `trader/strategy.py`, `trader/node.py` | Native Nautilus `Strategy`; broker-neutral `TradingNode`/backtest config + the live run/stop lifecycle | Lifecycle, bar-driven period rollover, futures roll refresh, FX quote mirroring into Cache marks, translating `OrderIntent`s into Nautilus orders, RiskEngine config, the `trader start`/`stop` daemon, and structured `self.log` records. IBKR client/connection config is **not** here — it lives in the one IBKR adapter (`aegis-data/ibkr.py`); `node.py` carries no broker vocabulary. |

## Dependency rule

```
domain/*            -> pure value objects and algorithms, no Nautilus
bundles/*           -> bundle registry and contract assembly, no Strategy lifecycle
trader/pipeline.py  -> domain + bundle/data/portfolio ports, no Strategy effects
trader/_rebalancer.py -> pure planning implementation of the pipeline (imports domain/*
                       only; no ports, no Nautilus lifecycle); imported by trader/pipeline.py
                       and nothing else
trader/strategy.py  -> Nautilus lifecycle and I/O effects over the pipeline
trader/node.py      -> broker-neutral Nautilus node + live run/stop lifecycle; no IBKR SDK
                       import and no ibg_*/IDEALPRO vocabulary — reaches IBKR only through the
                       single aegis_data.ibkr.attach_live_clients seam (lazy ibapi behind it)
backtest.py         -> backtest engine + non-live RiskEngine config (was trader/modes.py)
```

`data/market_data.py` and `portfolio/book_state.py` may import Nautilus facade types because the Trader is a Nautilus overlay and these ports intentionally hide Nautilus read trains. The Nautilus-free boundary that matters is `domain/*` plus the value-object surface returned by `RebalancePipeline`.

## Realized rebalance-pipeline shape

`RebalancePipeline` is the deep module ADR-0003 originally intended:

- `startup_check() -> StartupResult` runs the environment-dependent account-integrity gate. Structural Book invariants are already proven by `assemble_book`; a failed runtime gate returns a typed halt gate plus human reason, which the Strategy logs before idling.
- Identity needs no pipeline resolver: `AssembledBook.loadable_instrument_ids` is the proven, sorted union from every Execution Bundle, and IBKR's `InstrumentProvider.load_ids` resolves it at boot (root ADR-0007). The futures roll is driven by the Roll Desk over `aegis-data`'s `ContinuousContractModel` — live, keyed by `InstrumentId` — not by a pipeline resolution step.
- `rebalance_period(CompletedRebalancePeriod) -> RebalanceResult` reads completed-period windows and freshness through `MarketDataPort`, computes sleeve targets from Execution Bundles, builds the rebalance plan, sizes deltas, filters stale instruments, records the `SleeveLedger`, and returns `OrderIntent`s plus a `RebalanceSummary` carrying the real gate outcome. It is also the **test surface for all rebalance-planning behavior** (`tests/unit/test_rebalance_behavior.py` over the pipeline-seam harness): the plan builder, its value object, and the per-name breach error are private vocabulary of `trader/_rebalancer.py`, not a contract.
- The owned `SleeveLedger` supplies realized covariance for the next rebalance and end-of-run evidence (realized book skew and per-sleeve P&L attribution).

`RebalanceStrategy` is the thin Nautilus adapter around that shape. It wires cache-backed ports and the resolver at `on_start`, logs `StartupResult` / `RebalanceSummary` / end-of-run evidence through native `self.log`, subscribes bars and FX reference quotes, keeps the bar-driven period rollover trigger, refreshes futures rolls, and submits returned orders through Nautilus's own order factory and `ExecutionEngine`.

## Explicit non-ports

- **No `ExecutionPort`.** Order submission goes through Nautilus's venue-agnostic order factory, `ExecutionEngine`, and `RiskEngine` from the Strategy. IBKR-specific behavior belongs in the single IBKR adapter (`aegis-data/ibkr.py`) — connection-config translation only, building Nautilus's *stock* `InteractiveBrokers{Data,Exec}ClientConfig` + registering the stock live factories — not in the Trader's `node.py` or a Trader execution adapter.
- **No `ObservabilityPort`.** The shipped sink is Nautilus's native logger (`self.log`). A future subscriber-based backend should attach to Nautilus `MessageBus` (`publish_signal` / `publish_data`) rather than reintroducing a shallow Trader port.
- **No Cache wrapper.** Cache remains Nautilus's reconciled source of truth. Trader-owned state is limited to Roll Desk orchestration and the pure `SleeveLedger` observations; the continuous series state lives in `aegis-data`'s `ContinuousContractModel`.

## Directory layout

```
aegis_trader/
  bundles/book.py             # deep Book assembly -> AssembledBook
  bundles/{port,registry,stub}.py  # BundleRegistryPort + two adapters
  data/market_data.py          # MarketDataPort + NautilusMarketData
  domain/                      # pure algorithms and value types
  portfolio/book_state.py      # BookStatePort + NautilusBookState
  trader/
    pipeline.py                # StartupResult/RebalanceResult orchestration
    _rebalancer.py             # pipeline-private rebalance planning (ADR-0002 gates)
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

## Amendment — 2026-07-10 (aegis-rd-qllq): rebalance planning is internal to `RebalancePipeline`

`domain/rebalancer.py` moved to **`trader/_rebalancer.py`** — a private module
of the pipeline, its only importer. The module keeps its file decomposition,
its name (ADR-0002's "the rebalancer"), and its purity (imports `domain/*`
only; no ports, no Nautilus lifecycle); ADR-0002's gate behavior and ordering
moved verbatim. What changed is ownership: the nine-parameter
`rebalance_plan` seam had exactly one production caller — the pipeline, which
gathers every argument from state it already owns (bundle bands and owners,
ledger covariance and drawdown, its own applied sleeve weights) — so it failed
the deletion test as a public interface. `RebalancePlan` and
`PerNameExposureBreach` are now the private module's vocabulary; the pipeline's
own interface is unchanged.

Deleted with the seam, no shims (Forward-First):

- `rebalance()` — a deltas-only wrapper with zero production callers.
- the `realized_vols` parameter of `rebalance_plan` — production only ever
  feeds the allocator through the ledger's realized covariance; the
  allocator's own `realized_vols` routing (ADR-0004) is untouched.

**Test surface.** All rebalance-planning behavior is asserted through
`rebalance_period` in production observables — orders, `halt_reason`,
`GateOutcome`, summary counts, `last_sleeve_weights` — via the pipeline-seam
harness (`tests/support/rebalance_harness.py`, identity sizing: unit bars,
NAV 1e6). The migration was parity-protected: the new suite landed green
against the old public seam before the move, so the move commit is
behavior-neutral with the new suite as its oracle.

Considered and rejected:

- **Inline into `pipeline.py`** — a ~1,000-line module; the repo splits files
  well before that (cf. the validation split), and the planning/orchestration
  file decomposition is worth keeping. Privacy, not co-location, was the goal.
- **Underscore it in place (`domain/_rebalancer.py`)** — an ownership
  contradiction: a module private to the pipeline does not live in the shared
  domain layer its neighbors may import.
- **Keep the internal-seam tests** — rejected on the observability argument:
  assertions the production interface cannot express are pinning
  non-production observables, i.e. dead behavior. The migration proved this
  concretely: cross-sleeve overlap netting is unreachable (book assembly
  admits one band owner per instrument and bundle bands must equal the
  contract), a realized position outside every bundle contract can never
  become an order (no sizing metadata; filtered as stale), and the "empty
  target frame is silently skipped" behavior was never production-true — at
  the interface it crashes the period (latent bug aegis-rd-m4fv).

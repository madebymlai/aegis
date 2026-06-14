# Aegis Trader package architecture: deep modules behind ports over the Nautilus kernel

Status: accepted (greenfield scaffolding)

Aegis Trader is a NautilusTrader system (ADR-0001). NautilusTrader is itself a
**ports-and-adapters** kernel: the `NautilusKernel` composes the `MessageBus`, `Cache`,
`DataEngine`, `ExecutionEngine`, `RiskEngine`, and `Portfolio`, and the *same* `Strategy` /
`Actor` code runs unchanged across its three environments — **backtest, sandbox (paper),
live**. We mirror that discipline one level up: Aegis Trader is a **pure domain core that
depends only on its own ports**; **Nautilus-backed adapters** implement those ports; a
**thin `Strategy`** drives the core; a **runtime** wires it into the chosen environment. The
domain core imports **no** Nautilus types — Nautilus appears only in adapters, the
`Strategy`, and the runtime — so the alpha-to-orders logic stays a deep module:
broker-free-testable and provider-agnostic (DIP).

## Module map (the six concerns)

| # | Concern | Package | Port (abstraction) | Nautilus-backed adapter | Depth — what the module hides |
|---|---|---|---|---|---|
| 1 | **Data engine** | `data/` | `MarketDataPort` | `data/nautilus.py` | per-sleeve bar subscription by `BarType`, warmup to `DataContract.lookback_bars`, `Cache` reads, FIGI→`InstrumentId`, assembling each sleeve's `MarketDataBundle` as-of its latest completed bar |
| 2 | **Execution engine** (provider-agnostic) | `execution/` | `ExecutionPort` | `execution/nautilus.py` (+ `execution/ibkr.py` resolver) | `OrderIntent`→Nautilus order (next-close: plain `MARKET` on the execution bar in backtest, `AT_THE_CLOSE`/MOC live) submitted through Nautilus's **venue-agnostic `ExecutionEngine`** (routes by `InstrumentId`); `RiskEngine` order caps + kill-switch. **No broker API here** — IBKR enters only via Nautilus's *own* adapter interface: client-factory config in `trader/modes.py` and the FIGI→`InstrumentId` resolver (Nautilus IBKR `InstrumentProvider`), both swappable |
| 3 | **Portfolio** | `portfolio/` | `BookStatePort` | `portfolio/nautilus.py` | NAV-in-base, `net_position` per instrument, FX/pence marks — the sizing & realized-weight inputs, read from Nautilus `Portfolio`/`Account` |
| 4 | **Trader** | `domain/` + `trader/` | *(the core)* | `trader/strategy.py`, `trader/modes.py` | the **rebalancer** (net→gate→size→band→`OrderIntent`s), sizing, Book Config, the **pipeline**, and the **3 modes** |
| 5 | **MessageBus logging** | `observability/` | `ObservabilityPort` | `observability/nautilus.py` | tapping the `MessageBus` + `LoggingConfig` for structured logs and the **alerts** (quarantine, global halt, rebalance summary) |
| 6 | **Cache** | — *(Nautilus substrate)* | consumed via #1/#3 | Nautilus `Cache` | reconciled positions/orders/account — the single source of truth (ADR-0001). **Not re-wrapped**: a 1:1 pass-through would be a shallow module (YAGNI). The only Trader-owned cache is the regenerable Security-Master FIGI↔`InstrumentId` bimap, inside `bundles/` |

A seventh internal package, **`bundles/`** (`BundleRegistryPort` + entry-point discovery +
the `aegis-runtime` Security Master), supports #2/#4: it loads the `ExecutionBundle` for a
Book-Config wheel filename and exposes its `DataContract` + provenance.

## Dependency rule (the DIP spine)

```
domain/*            ──→  */port.py                     (abstractions only — no Nautilus, no adapters)
trader/pipeline.py  ──→  domain/* + */port.py          (orchestration — no Nautilus)
*/nautilus.py, */ibkr.py, trader/strategy.py, trader/modes.py  ──→  Nautilus + ports
bundles/            ──→  aegis-runtime (Security Master, Allocation Policy validator)
```

- The **rebalancer** (`domain/rebalancer.py`) is a pure function
  `(sleeve weights, budgets, caps, bands, BookState, FX) → OrderIntent[]` — no Nautilus, no
  I/O. **This is the high test seam**, the analogue of the bundle's `compute_weights` fidelity
  seam.
- Nautilus types never cross into `domain/`. A port speaks domain identities (`Figi`,
  `InstrumentRef`); resolution to a Nautilus `InstrumentId` happens *inside* the adapter.

## Directory layout

```
aegis-trader/
  pyproject.toml                # setuptools; deps: aegis-runtime, nautilus_trader, pydantic
  aegis_trader/
    domain/                     # pure — no Nautilus, no I/O
      types.py                  # value objects: Figi, SleeveName, Budget, Band(up,down), TargetWeight, OrderIntent
      book_config.py            # Book Config (pydantic): sleeve → wheel filename, budgets, caps, bands, base ccy
      rebalancer.py             # net → gate(realized) → size → band → OrderIntent[]   (HIGH SEAM)
      sizing.py                 # weight → qty: NAV / FX / pence
    data/        { port.py, nautilus.py }            # #1
    execution/   { port.py, nautilus.py, ibkr.py }   # #2  nautilus.py = venue-neutral over the ExecutionEngine; ibkr.py = the one IBKR venue adapter (resolver)
    portfolio/   { port.py, nautilus.py }            # #3
    observability/ { port.py, nautilus.py }          # #5
    bundles/     { port.py, registry.py }            # entry-point discovery + Security Master
    trader/                                          # #4 orchestration + modes
      pipeline.py               # trigger → data(port) → bundles → rebalancer → execution(port)
      strategy.py               # RebalanceStrategy(nautilus Strategy): thin adapter driving the pipeline
      modes.py                  # backtest | paper | live  → builds the matching Nautilus node
      cli.py                    # `aetrade` entry point
  tests/
    unit/         # domain core (rebalancer fidelity, sizing, book_config) — zero Nautilus
    integration/  # adapters vs fakes / BacktestEngine
    e2e/          # full BacktestNode run on synthetic data
    fixtures/
```

Each concern package keeps its **port in a separate module from its adapter**, so importing
the port never drags in Nautilus.

## Three modes — one Strategy, three environments

`trader/modes.py` builds the right Nautilus node; the `RebalanceStrategy` and every port are
identical across modes (Nautilus guarantees backtest→live code parity):

- **backtest** → `BacktestNode` over a Parquet catalog / synthetic data, `TestClock`. Validates
  the *overlay* (netting, bands, sizing, reconciliation) that RD never scores; also the e2e seam.
- **paper** → `TradingNode` in `Environment.SANDBOX` against IBKR paper (`FROZEN` data, paper
  account), `LiveClock`.
- **live** → the same node in `Environment.LIVE` against the IBKR live account.

Only the node/clients/environment change; the domain core and ports are untouched — **what you
backtest is what you trade.**

## Where each prior decision lands

- FIGI + Security Master (root ADR-0002) → `bundles/` (+ `aegis-runtime`).
- Realized-book gate, asymmetric bands, union-gate/quarantine (ADR-0002) → `domain/rebalancer.py`.
- Sizing NAV/FX/pence (ADR-0001) → `domain/sizing.py` + `portfolio/`.
- Per-sleeve timeframe cadence + next-close (ADR-0001) → `trader/strategy.py` (subscribe per
  sleeve `BarType`) + `execution/`.
- Reconciliation 2×2 — account-integrity → global halt; unknown instrument → quarantine
  (ADR-0001) → `trader/pipeline.py` (halt), `portfolio/` (integrity check),
  `domain/rebalancer.py` (quarantine).
- `RiskEngine` order caps + kill-switch (ADR-0001) → `execution/` config.
- Book Config, sleeve→wheel-filename (ADR-0001) → `domain/book_config.py`.

## Considered options

- **Flat `aegis_trader/` package** (the earlier proposal): rejected. It muddles the dependency
  direction — domain logic and Nautilus wiring sit side by side, so nothing stops a Nautilus
  import leaking into the rebalancer and the high seam loses its boundary. The layered split
  costs a few directories and buys the DIP guarantee.
- **Re-wrap every Nautilus kernel component** as our own DataEngine/ExecutionEngine/Portfolio/
  Cache/MessageBus: rejected where it adds no depth. A wrapper forwarding 1:1 to Nautilus is a
  *shallow* module — the opposite of the goal. We add a port **only** where it hides
  substantial work (data→`MarketDataBundle`, provider-agnostic execution, book-state reads,
  observability); `Cache` is consumed directly as substrate.
- **Let the `Strategy` hold the logic** (the classic Nautilus pattern): rejected. It couples
  alpha-to-orders to the framework and to live I/O, making the core untestable without a node.
  The `Strategy` is a thin adapter delegating to the pure pipeline.

## Consequences

- **The rebalancer is unit-testable with zero Nautilus** — synthetic weights/positions/NAV in,
  `OrderIntent`s out. Adapters are integration-tested against fakes or a `BacktestEngine`; the
  whole stack via a `BacktestNode` e2e run.
- **Venue access goes through Nautilus's *own* adapter interface, not a parallel one.** Domain,
  ports, the `Strategy`, and execution *translation* use only Nautilus's venue-agnostic API
  (`InstrumentId`, `order_factory`, the `ExecutionEngine`'s routing, `InstrumentProvider`).
  **IBKR is one implementation**, isolated to exactly two swappable places: client-factory
  config in `trader/modes.py`, and the FIGI→`InstrumentId` resolver behind the Security Master.
  No hand-rolled broker API; no broker-specific import in `domain/`, `ports/`, the `Strategy`,
  or execution translation.
- **Provider-agnostic execution:** a second venue is a new Nautilus adapter config + a resolver
  impl; the domain and the other five concerns are untouched (OCP).
- **No primitive obsession:** domain value types (`Figi`, `SleeveName`, `Budget`,
  `Band(up,down)`, `TargetWeight`, `OrderIntent`) replace raw strings/floats across the ports.
- **Cache stays Nautilus's** — one reconciled source of truth, no parallel ledger; the sole
  Trader cache is the regenerable Security-Master bimap.
- **`pydantic` validates the Book Config** (mirrors RD ADR-0012); **VBT PRO is transitive**
  (arrives with installed bundle wheels), not a direct Trader dependency.
- **Backtest = live parity** is inherited from Nautilus: the overlay validated in `backtest`
  mode is byte-for-byte what runs in `paper`/`live`.

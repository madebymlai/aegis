# Aegis Context Map

Aegis is a monorepo of bounded contexts for systematic trading. Each context
owns its own glossary (`CONTEXT.md`) and decision log (`docs/adr/`); this map
records what the contexts are and how they relate.

## Contexts

- [Aegis RD](./aegis-rd/CONTEXT.md) — research operating system that turns
  market hypotheses into reproducible, scored evidence and promotes validated
  strategies.
- [Aegis Trader](./aegis-trader/CONTEXT.md) — live execution context that
  trades strategies promoted by Aegis RD against real venues. It runs a
  **Commingled Book** of **Sleeves**, sized by a risk-budgeting **Allocator**,
  both offline through Nautilus' `BacktestEngine` and live against Interactive
  Brokers — the same rebalance path for backtest, paper, and live (ADR-0001).
- [Aegis Data](./aegis-data/CONTEXT.md) — shared market-data context that owns
  one durable **Catalog**, stores Nautilus-native bars by **InstrumentId**, and
  serves both research sourcing and live warmup through the same DataProvider
  port.
- **`aegis-runtime`** — shared runtime (shared kernel) that executes one Locked
  **Candidate**: component loading, the single-candidate (`force_locked`,
  `n_candidates=1`) orchestration, and **Exposure Validation** over native
  **InstrumentId** columns. Depended on by both Aegis RD and every
  **Execution Bundle**, so the research apparatus (optimizer, Candidate Store,
  preflight, ranking) never crosses into execution. _(top-level package
  `aegis-runtime/`; Aegis RD depends on it today, Aegis Trader will once it
  exists)_

## Relationships

- **Aegis RD → Aegis Trader**: Aegis RD is the system of record for *which*
  strategies are worth trading and *with what parameters*. It promotes a
  validated strategy as a **Lock** — a `run_id[:role]` reference that
  reproduces one scored **Candidate** with its exact parameters and
  **Provenance**, resolved against Aegis RD's **Candidate Store**. Aegis Trader
  is the downstream consumer: it installs a promoted strategy and executes it
  (live or in backtest) rather than re-deriving parameters.

  The handoff crosses the boundary as an **Execution Bundle** (ADR-0001):
  `aerd export` resolves a Lock, bakes the Candidate's parameters, and builds a
  versioned uv wheel carrying the strategy + wired indicators + **Provenance**.
  Aegis Trader installs the wheel and runs it through **`aegis-runtime`**,
  supplying Nautilus **InstrumentId**-keyed market data; the bundle computes and
  gates — with no **Candidate Store** access at runtime.

- **Aegis RD → Aegis Data**: Aegis RD declares native Nautilus
  **InstrumentIds** in its **Run Config**. Aegis Data serves Raw Bars from the
  Catalog, lazily filling Coverage Gaps through the DataProvider port.

- **Aegis Trader → Aegis Data**: Aegis Trader backtests read historical bars for
  the **InstrumentId** values baked into each **Execution Bundle**. Trader does
  not select a universe by provider ticker.

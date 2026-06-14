# Aegis Context Map

Aegis is a monorepo of bounded contexts for systematic trading. Each context
owns its own glossary (`CONTEXT.md`) and decision log (`docs/adr/`); this map
records what the contexts are and how they relate.

## Contexts

- [Aegis RD](./aegis-rd/CONTEXT.md) — research operating system that turns
  market hypotheses into reproducible, scored evidence and promotes validated
  strategies.
- [Aegis Trader](./aegis-trader/CONTEXT.md) — live execution context that
  trades strategies promoted by Aegis RD against real venues. _(stub — only the
  handoff contract is designed; see ADR-0001)_
- **`aegis-runtime`** — shared runtime (shared kernel) that executes one Locked
  **Candidate**: component loading, the single-candidate (`force_locked`,
  `n_candidates=1`) orchestration, currency conversion, and the **Allocation
  Policy** gate. Depended on by both Aegis RD and every **Execution Bundle**, so
  the research apparatus (optimizer, Candidate Store, preflight, ranking) never
  crosses into execution. _(planned — not yet carved out of Aegis RD)_

## Relationships

- **Aegis RD → Aegis Trader**: Aegis RD is the system of record for *which*
  strategies are worth trading and *with what parameters*. It promotes a
  validated strategy as a **Lock** — a `run_id[:role]` reference that
  reproduces one scored **Candidate** with its exact parameters and
  **Provenance**, resolved against Aegis RD's **Candidate Store**. Aegis Trader
  is the intended downstream consumer: it takes a promoted strategy and
  executes it live rather than re-deriving parameters.

  The handoff crosses the boundary as an **Execution Bundle** (ADR-0001):
  `aerd export` resolves a Lock, bakes the Candidate's parameters, and builds a
  versioned uv wheel carrying the strategy + wired indicators + **Provenance**.
  Aegis Trader installs the wheel and runs it through **`aegis-runtime`**,
  supplying native-currency market data and FX series; the bundle converts to
  base currency, computes, and gates — with no **Candidate Store** access at
  runtime.

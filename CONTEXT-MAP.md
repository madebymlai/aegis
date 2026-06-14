# Aegis Context Map

Aegis is a monorepo of bounded contexts for systematic trading. Each context
owns its own glossary (`CONTEXT.md`) and decision log (`docs/adr/`); this map
records what the contexts are and how they relate.

## Contexts

- [Aegis RD](./aegis-rd/CONTEXT.md) — research operating system that turns
  market hypotheses into reproducible, scored evidence and promotes validated
  strategies.
- [Aegis Trader](./aegis-trader/CONTEXT.md) — live execution context that
  trades strategies promoted by Aegis RD against real venues. _(stub — design
  not yet resolved)_

## Relationships

- **Aegis RD → Aegis Trader**: Aegis RD is the system of record for *which*
  strategies are worth trading and *with what parameters*. It promotes a
  validated strategy as a **Lock** — a `run_id[:role]` reference that
  reproduces one scored **Candidate** with its exact parameters and
  **Provenance**, resolved against Aegis RD's **Candidate Store**. Aegis Trader
  is the intended downstream consumer: it takes a promoted strategy and
  executes it live rather than re-deriving parameters.

  _The precise handoff contract — what crosses the boundary between research
  and execution, and in what form — is unresolved. Pin it down with
  `/grill-with-docs` before building Aegis Trader._

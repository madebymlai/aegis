# Aegis

Aegis is a monorepo of bounded contexts for systematic trading — from research
through live execution. Each context owns its own glossary (`CONTEXT.md`) and
decision log (`docs/adr/`); the [Context Map](./CONTEXT-MAP.md) records what the
contexts are and how they relate.

## Contexts

### [`aegis-rd/`](./aegis-rd) — Research
A research operating system that turns market hypotheses into reproducible,
scored evidence. Every run writes an immutable manifest recording config,
environment, artifact hashes, and lineage, and promotes validated strategies as
**Locks** that reproduce an exact scored **Candidate**. See
[`aegis-rd/README.md`](./aegis-rd/README.md) and
[`aegis-rd/CONTEXT.md`](./aegis-rd/CONTEXT.md).

### [`aegis-trader/`](./aegis-trader) — Live execution _(stub)_
Trades strategies promoted by Aegis RD against real venues. Not yet designed —
see [`aegis-trader/CONTEXT.md`](./aegis-trader/CONTEXT.md).

## How they relate

Aegis RD is the system of record for *which* strategies are worth trading and
*with what parameters*. It promotes a validated strategy as a **Lock** — a
`run_id[:role]` reference that reproduces one scored **Candidate** with its exact
parameters and provenance. Aegis Trader is the intended downstream consumer: it
executes a promoted strategy live rather than re-deriving parameters. The precise
handoff contract between research and execution is still being designed.

## Layout

```
aegis/
├── CONTEXT-MAP.md     # the contexts and their relationships
├── aegis-rd/          # research operating system (mature)
└── aegis-trader/      # live execution (stub)
```

## Documentation

- [Context Map](./CONTEXT-MAP.md) — bounded contexts and their relationships
- Per-context glossaries: [`aegis-rd/CONTEXT.md`](./aegis-rd/CONTEXT.md), [`aegis-trader/CONTEXT.md`](./aegis-trader/CONTEXT.md)
- Architecture decisions: [`aegis-rd/docs/adr/`](./aegis-rd/docs/adr)

# Aegis RD

<p align="center">
  <img src="docs/assets/hero.png" alt="Aegis RD" width="830">
</p>

Aegis RD is the Strategy Research context. It gives every hypothesis the same evidence lifecycle and preserves the identity of every Candidate that survives it.

## Research Lifecycle

1. Declare a Research Hypothesis as reviewed Components and a Run Config.
2. Load one coherent market-data window for the declared Instrument IDs.
3. Materialize complete Candidate parameterizations.
4. Replay every Candidate over one shared Development Period.
5. Compare Metrics across Observation Blocks and the complete period.
6. Commit the best, median, and worst representatives as one Candidate Set.
7. Lock a Candidate when it is ready for exact reuse or export.

The unit of evidence is the complete Candidate. Indicator quality, Strategy behavior, portfolio assumptions, costs, and data identity travel together.

## Commands

- `aerd run <config>` evaluates a Run Config and returns its Candidate Set and Lock handles.
- `aerd show <topic>` displays the current authoring vocabulary and available Components.
- `aerd export <config>` prepares an Execution Bundle from a locked Candidate.

## Research Contract

A Run Config declares:

- Instrument IDs and required Market Arrays
- Indicator and Strategy Components
- Candidate parameter spaces
- portfolio assumptions and Exposure Limits
- ranking Metrics and Observation Blocks

A successful Run leaves durable Candidate evidence. A failed Run reports its failure against the same declared research question.

## Handoff

A Lock names one Candidate. Export turns that locked evidence into an Execution Bundle containing the strategy contract required by Strategy Runtime and Portfolio Execution.

## Documentation

- [Strategy Research glossary](./CONTEXT.md)
- [Aegis Context Map](../CONTEXT-MAP.md)
- [Market Data](../aegis-data)
- [Strategy Runtime](../aegis-runtime)

<p align="center">
  <a href="https://vectorbt.pro/">
    <img src="docs/assets/disclaimer.svg" alt="VectorBT PRO license required" width="830">
  </a>
</p>

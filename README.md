# Aegis

Aegis is a systematic strategy lifecycle. It turns market hypotheses into reproducible evidence, carries selected strategies across a locked runtime contract, and combines them into one risk-budgeted portfolio.

## Architecture Overview

<p align="center">
  <img src="docs/assets/architecture.png" width="900" alt="Aegis architecture across evidence, decisions, and portfolio control. Market Data supplies every plane. Strategy Research locks evidence into an Execution Bundle. Strategy Runtime produces a Sleeve Target. Portfolio Execution combines sleeve targets with Book State to prepare orders, while fills and reconciliation update the Book.">
</p>

The lifecycle preserves three things across every boundary: instrument identity, strategy intent, and exposure limits.

## Contexts

### [Strategy Research](./aegis-rd)

Evaluates market hypotheses as comparable Candidates. A successful Run commits representative evidence and can Lock one Candidate for exact reuse.

### [Market Data](./aegis-data)

Owns Instrument identity, market observations, historical coverage, and continuous-futures history for every downstream context.

### [Strategy Runtime](./aegis-runtime)

Applies an Execution Bundle to a coherent Market Data Bundle and produces an exposure-validated Target Book.

### [Portfolio Execution](./aegis-trader)

Treats each Execution Bundle as a Sleeve, allocates risk across Sleeves, nets their targets into one Commingled Book, and prepares the resulting orders.

## Strategy Lifecycle

1. A Research Hypothesis becomes a Strategy and a Run Config.
2. A Run evaluates complete Candidates over one Development Period.
3. A Candidate Set preserves representative evidence across the search space.
4. A Lock selects one Candidate and produces an Execution Bundle.
5. Strategy Runtime converts current market data into signed Target Weights.
6. Portfolio Execution allocates, nets, controls, and rebalances the Book.

## Repository

```text
aegis/
├── aegis-rd/       Strategy Research
├── aegis-data/     Market Data
├── aegis-runtime/  Strategy Runtime
└── aegis-trader/   Portfolio Execution
```

## Domain Documentation

- [Context Map](./CONTEXT-MAP.md)
- [Strategy Research glossary](./aegis-rd/CONTEXT.md)
- [Market Data glossary](./aegis-data/CONTEXT.md)
- [Strategy Runtime glossary](./aegis-runtime/CONTEXT.md)
- [Portfolio Execution glossary](./aegis-trader/CONTEXT.md)

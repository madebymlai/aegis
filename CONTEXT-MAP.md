# Aegis Context Map

Aegis carries systematic strategies from market evidence to portfolio decisions. Each context owns a distinct part of that lifecycle and exchanges a small set of stable domain contracts.

## Contexts

- [Strategy Research](./aegis-rd/CONTEXT.md): tests hypotheses, compares strategy candidates, and locks reproducible evidence.
- [Market Data](./aegis-data/CONTEXT.md): owns instrument identity, market observations, historical coverage, and continuous futures.
- [Strategy Runtime](./aegis-runtime/CONTEXT.md): evaluates a locked strategy against a declared market-data contract and produces a target book.
- [Portfolio Execution](./aegis-trader/CONTEXT.md): combines strategy sleeves into one risk-budgeted book and turns target changes into orders.

## Relationships

- **Market Data to Strategy Research**: Strategy Research requests market-data windows for identified instruments and records the data identity with each Candidate.
- **Strategy Research to Strategy Runtime**: A Lock selects a Candidate. An Execution Bundle carries that Candidate's strategy definition, parameters, data contract, and exposure limits.
- **Market Data to Strategy Runtime**: Market Data supplies the observations and instrument definitions required by an Execution Bundle.
- **Strategy Runtime to Portfolio Execution**: Strategy Runtime produces signed target weights for one Sleeve. Portfolio Execution scales and combines those targets.
- **Market Data to Portfolio Execution**: Portfolio Execution uses current observations and instrument definitions to value the Book, manage continuous futures, and prepare orders.

## Shared Language

- **Instrument ID** is the common identity for market data, strategy targets, positions, and orders.
- **Execution Bundle** is the contract between Strategy Research and the downstream runtime.
- **Target Weight** is the contract between Strategy Runtime and Portfolio Execution.
- **Exposure Limits** constrain both an individual strategy and the combined Book.

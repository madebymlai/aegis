# Aegis Data

Aegis Data is the Market Data context. It gives research and portfolio execution one identified history of instruments, observations, coverage, and futures rolls.

## What It Owns

- Instrument IDs and Instrument Definitions
- Market Streams and bounded Data Windows
- durable Catalog coverage
- external Data Provider boundaries
- Continuous Futures, Dated Contracts, Rolls, and Rebasing

## Data Lifecycle

```text
Instrument Definition
        +
Market Observations
        |
        v
     Catalog
      /   \
     v     v
Research  Portfolio Execution
```

A consumer asks for a Data Window using Instrument IDs and Market Streams. Existing Catalog coverage is read directly. A Data Provider can extend missing coverage. The resulting observations retain the same identities throughout the strategy lifecycle.

## Continuous Futures

A Continuous Future joins successive Dated Contracts through a shared Roll Agreement. Rebasing keeps the historical series on a consistent price basis as the Front Contract changes.

The Roll Agreement is shared across research and portfolio execution, which keeps strategy evidence and live portfolio decisions aligned on the same contract sequence.

## Documentation

- [Market Data glossary](./CONTEXT.md)
- [Aegis Context Map](../CONTEXT-MAP.md)
- [Strategy Research](../aegis-rd)
- [Portfolio Execution](../aegis-trader)

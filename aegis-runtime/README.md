# Aegis Runtime

Aegis Runtime is the Strategy Runtime context. It preserves the decision contract of a locked Candidate wherever that strategy is evaluated.

## Contract

```text
Execution Bundle + Market Data Bundle
                  |
                  v
          Locked Execution Plan
                  |
                  v
              Target Book
```

An Execution Bundle declares the Strategy, fixed parameters, required market data, currency basis, and Exposure Limits. A satisfying Market Data Bundle produces signed Target Weights for the declared instruments.

## Shared Guarantees

- The Locked Execution Plan stays fixed across research and portfolio execution.
- The Data Contract defines every required instrument and Market Array.
- Currency Conversion expresses the decision in the Book's base currency.
- Exposure Limits gate every Target Book.
- Drift Bands carry the reviewed tolerance around Target Weights.

Strategy Runtime forms the narrow seam between Candidate evidence and portfolio decisions. Candidate search and Book allocation remain in their owning contexts.

## Documentation

- [Strategy Runtime glossary](./CONTEXT.md)
- [Aegis Context Map](../CONTEXT-MAP.md)
- [Strategy Research](../aegis-rd)
- [Portfolio Execution](../aegis-trader)

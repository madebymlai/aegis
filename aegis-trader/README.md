# Aegis Trader

Aegis Trader is the Portfolio Execution context. It combines locked strategy Sleeves into one Commingled Book and turns portfolio decisions into orders.

## Portfolio Model

Each Sleeve binds a name and Risk Group to one Execution Bundle. Risk Shares express the intended volatility budget. The Allocator scales Sleeve targets, and the Book combines overlapping instrument exposures into one portfolio target.

The three Risk Groups describe each Sleeve's role:

- **Floor** supplies the persistent return-seeking base.
- **Target** supplies deliberately budgeted convexity or protection.
- **Expansion** holds capacity for approved extensions to the Book.

## Rebalance Flow

```text
Execution Bundles
       |
       v
Sleeve Target Books
       |
       v
Allocator and Book Controls
       |
       v
Combined Book Target
       |
       v
Rebalance Plan
       |
       v
Order Intents
```

A Rebalance observes current Book state, refreshes due Sleeve targets, applies risk allocation and drawdown controls, checks exposure and drift, and prepares the weight changes required by the approved Book target.

## Book Controls

- Book Volatility Target
- Gross, net, and per-Instrument exposure limits
- Sleeve and Instrument Drift Bands
- Drawdown Delever Curve
- Tail Convexity Budget
- financing, distributions, and transaction costs

The Sleeve Ledger records Book Observations for realized risk, attribution, drawdown, and portfolio analytics.

## Commands

- `aegis-trader backtest --start <date> --end <date>` evaluates the configured Book over historical market data.
- `aegis-trader trader start` starts portfolio execution for the configured Book.
- `aegis-trader trader stop` requests an orderly stop.

Book composition lives in the Book Config. Account credentials and venue connectivity belong to the deployment environment.

## Documentation

- [Portfolio Execution glossary](./CONTEXT.md)
- [Aegis Context Map](../CONTEXT-MAP.md)
- [Market Data](../aegis-data)
- [Strategy Runtime](../aegis-runtime)

---
title: Use Stop Parameters and Priority Rules Explicitly
date: 2026-05-17
category: best-practices
module: vectorbtpro.portfolio
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - adding stop loss take profit or trailing stops to from_signals
  - reviewing how multiple stop types interact
  - configuring trailing stop activation thresholds
tags:
  - vectorbtpro
  - stop-loss
  - take-profit
  - trailing-stop
  - from-signals
---

# Use Stop Parameters and Priority Rules Explicitly

## Context

VectorBT supports fixed stop loss, take profit, and trailing stop behavior through portfolio parameters, but the semantics are easy to blur. In Discord, the maintainer clarified that `tsl_th` is the activation threshold for a trailing stop and uses the same format as `tsl_stop`.

The maintainer also pointed to the documented stop priority: if multiple stops are hit, the simulator assumes stop loss first, then trailing stop or trailing take profit, then take profit. The earliest pending stop is executed and the others are canceled.

## Guidance

Configure trailing stops with both the activation threshold and trailing distance:

```python
pf = vbt.Portfolio.from_signals(
    close=close_price,
    entries=entries,
    exits=exits,
    init_cash="auto",
    tsl_th=0.10,
    tsl_stop=0.10,
)
```

This means the trailing stop activates once profit reaches 10%, and the trailing distance is 10%.

When using several stop types together, document the intended precedence:

```python
pf = vbt.Portfolio.from_signals(
    close=close_price,
    entries=entries,
    exits=exits,
    sl_stop=0.05,
    tsl_th=0.10,
    tsl_stop=0.05,
    tp_stop=0.20,
)
```

Review results with the priority rule in mind: SL first, then TSL/TTP, then TP, with only the earliest pending stop executed.

## Why This Matters

Stop configuration changes trade outcomes and can make a strategy look materially different. If a backtest combines fixed SL, TP, and trailing stops without documenting activation and priority, future readers may assume a different execution path than the simulator used.

## When to Apply

- Apply this whenever `sl_stop`, `tp_stop`, `tsl_th`, or `tsl_stop` appear together.
- Apply this when a trailing stop should activate only after a profit threshold.
- Apply this when explaining why one stop executed while another possible stop did not.

## Examples

Trailing stop activates after 10% profit:

```python
tsl_th = 0.10
tsl_stop = 0.10
```

Fixed SL and TP with trailing stop:

```python
sl_stop = 0.05
tp_stop = 0.20
tsl_th = 0.10
tsl_stop = 0.05
```

Review question: "If two stops could have been hit, which one does VectorBT consider first?"

## Related

- Discord thread on trailing stop parameters and stop priority: https://discord.com/channels/918629562441695344/918629563469295628/1208340656150544464
- [Model Execution Timing Explicitly in VectorBT Backtests](./vectorbt-execution-timing-nextopen-2026-05-17.md)

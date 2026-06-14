---
title: Avoid Same-Bar Stop Assumptions in from_signals
date: 2026-05-17
category: logic-errors
module: vectorbtpro.portfolio
problem_type: logic_error
component: tooling
symptoms:
  - A trade shows positive PnL even though an entry-bar stop should have triggered
  - Tight stop losses appear ignored when using limit entries
  - Stop behavior differs from live fills on the same candle as entry
root_cause: wrong_api
resolution_type: workflow_improvement
severity: high
tags:
  - vectorbtpro
  - from-signals
  - stop-loss
  - same-bar
  - limit-orders
---

# Avoid Same-Bar Stop Assumptions in from_signals

## Problem

`Portfolio.from_signals` has an important limitation for same-bar behavior: it cannot execute two orders in the same bar. If a limit entry fills and a tight stop would also trigger inside that same bar, the stop can be ignored because the second order cannot execute on that bar.

## Symptoms

- A trade that should have stopped out on the entry candle remains open or later exits at take profit.
- The issue appears with tight stops, limit orders, or intrabar OHLC movement.
- The backtest does not match a live execution where the stop triggered seconds after entry.

## What Didn't Work

- Assuming OHLC values inside the same candle can model an entry and immediate stop as two separate events.
- Using `from_signals` with non-close entry prices and very tight stops while expecting tick-like event ordering.

## Solution

Use `from_signals` for cases where the entry price is close enough to the close-bar model, or where same-bar stop execution is not material. If same-bar entry-stop sequencing matters, use one of these approaches:

- Use higher-resolution data so entry and stop occur on separate rows.
- Delay stop activation until the next bar if that matches the intended model.
- Use a custom simulation/order function that models intrabar event ordering explicitly.
- Avoid limit-entry plus tight-stop setups in `from_signals` when the strategy depends on same-bar stop execution.

Example conservative guardrail:

```python
# Avoid modeling entry-bar stops when using close-level signal simulation.
entries = raw_entries.shift(1).fillna(False)

pf = vbt.Portfolio.from_signals(
    open=open_,
    high=high,
    low=low,
    close=close,
    entries=entries,
    sl_stop=sl_stop,
    tp_stop=tp_stop,
)
```

If the setup needs limit-order microstructure, make that a custom simulation concern rather than relying on `from_signals` defaults.

## Why This Works

The limitation is not about whether the OHLC range contains the stop price. It is about whether the simulator can represent both the entry order and the stop order as separate executions in the same row. Higher-resolution data or custom event ordering gives the simulator separate timestamps or explicit sequencing.

## Prevention

- Add a review step for strategies with tight stops, limit entries, or intrabar assumptions.
- Treat same-bar stop behavior as a model limitation unless a test proves the intended behavior.
- Prefer more granular data when stop distances are smaller than typical candle ranges.

## Related Issues

- Discord support thread on ignored same-bar stop after limit entry: https://discord.com/channels/918629562441695344/918630948248125512/1261407423068110979
- [Use Stop Parameters and Priority Rules Explicitly](../best-practices/vectorbt-stop-priority-and-trailing-stops-2026-05-17.md)

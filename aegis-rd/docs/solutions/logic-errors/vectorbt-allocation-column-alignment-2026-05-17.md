---
title: Align Allocation Columns Before VectorBT Portfolio Simulation
date: 2026-05-17
category: logic-errors
module: vectorbtpro.portfolio
problem_type: logic_error
component: tooling
symptoms:
  - Backtest results change after pandas version changes even though strategy logic is unchanged
  - Allocation dataframe columns do not match close price dataframe columns in the same order
  - Portfolio orders appear assigned to the wrong symbols or produce unexpected performance
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags:
  - vectorbtpro
  - pandas
  - column-alignment
  - allocations
  - from-orders
---

# Align Allocation Columns Before VectorBT Portfolio Simulation

## Problem

VectorBT portfolio inputs that represent the same assets must use the same columns in the same order. A Discord bug report noted that after pandas 2.2, dataframe operations involving empty frames could reorder columns alphabetically, causing allocation columns and close-price columns to diverge.

## Symptoms

- Backtest results change after a pandas upgrade without an intentional strategy change.
- `allocations_df.columns.equals(close_prices_df.columns)` returns `False`.
- Orders, allocations, or performance look like weights were applied to the wrong assets.

## What Didn't Work

- Relying on pandas to preserve column order through intermediate dataframe operations. The reported issue came from `pandas.DataFrame.add` with an empty dataframe, where pandas 2.2 created columns alphabetically while older behavior preserved the non-empty dataframe order.
- Assuming VectorBT will infer the intended asset mapping if `close` and `size` have the same labels but different order.

## Solution

Normalize allocation columns to the close-price dataframe immediately before simulation.

```python
close_prices_df = close_prices_df.sort_index()
allocations_df = allocations_df.reindex(index=close_prices_df.index, columns=close_prices_df.columns).fillna(0)

if not allocations_df.columns.equals(close_prices_df.columns):
    raise ValueError("Allocation columns must match close price columns")

portfolio = vbt.Portfolio.from_orders(
    close=close_prices_df,
    size=allocations_df,
    init_cash=100_000,
    size_type="targetpercent",
    group_by=True,
    cash_sharing=True,
    call_seq="auto",
    freq="D",
)
```

For stricter checks, also verify that no expected symbol disappeared during reindexing:

```python
missing_symbols = allocations_df.columns.difference(close_prices_df.columns)
if len(missing_symbols) > 0:
    raise ValueError(f"Allocations include symbols missing from close prices: {missing_symbols.tolist()}")
```

## Why This Works

Target-percent orders are array-like inputs. Even when labels exist, portfolio construction is safest when every asset-shaped input is explicitly conformed to the same index and column contract. Reindexing makes the mapping from weight to price column unambiguous and resistant to pandas ordering changes.

## Prevention

- Add an assertion before every reusable `Portfolio.from_orders` wrapper.
- Reindex weights to `close.columns` as the final step before simulation.
- Treat pandas upgrades as a reason to re-run a small known-output portfolio test.

Example test:

```python
assert allocations_df.index.equals(close_prices_df.index)
assert allocations_df.columns.equals(close_prices_df.columns)
```

## Related Issues

- Discord bug report on pandas 2.2 column ordering and `Portfolio.from_orders`: https://discord.com/channels/918629562441695344/918629995415502888/1261089171033030779
- [Diagnose NoCash Rejections in Target-Percent Rebalancing](../best-practices/vectorbt-targetpercent-nocash-rejections-2026-05-17.md)

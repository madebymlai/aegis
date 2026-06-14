---
title: Scale Large from_signals Runs with Chunking and Memory Budgets
date: 2026-05-17
category: performance-issues
module: vectorbtpro.portfolio
problem_type: performance_issue
component: tooling
symptoms:
  - Portfolio.from_signals runs take hours on large rows by columns matrices
  - MemoryError or allocation failed appears even when apparent RSS is lower than RAM
  - Threadpool chunking speeds up some runs but crashes others
root_cause: logic_error
resolution_type: workflow_improvement
severity: high
tags:
  - vectorbtpro
  - performance
  - chunking
  - memory
  - from-signals
  - max-order-records
---

# Scale Large from_signals Runs with Chunking and Memory Budgets

## Problem

Large `Portfolio.from_signals` runs scale with the target matrix shape. Millions of rows multiplied by thousands of columns can require large internal arrays and order-record buffers. Chunking can help, but it must be tuned to the data size, platform, and concurrency model.

## Symptoms

- Backtests with `rows x cols` shapes run for hours or fail with allocation errors.
- `chunked="threadpool"` is faster for some chunk sizes but unstable for others.
- Multiple processes plus threadpool chunking oversubscribe CPU or memory bandwidth.

## What Didn't Work

- Expecting `from_signals_nb` to reduce memory usage by itself.
- Running every parameter combination in one giant portfolio object.
- Treating `chunked="threadpool"` as a universal speedup without testing chunk sizes.

## Solution

Start with a measurable memory budget. Log rows, columns, dtype, expected signal density, elapsed time, RSS/commit, and whether chunking is enabled.

Use explicit chunking parameters instead of a bare string when tuning:

```python
pf = vbt.Portfolio.from_signals(
    close,
    entries=entries,
    exits=exits,
    chunked=dict(engine="threadpool", chunk_len=8),
    max_order_records=expected_order_records,
)
```

For parameterized sweeps, use mono-chunking so parameter combinations are split into manageable batches:

```python
@vbt.parameterized(merge_func="concat", mono_chunk_len=1000)
def backtest(close, sl_stop, tp_stop):
    return vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        sl_stop=vbt.Param(sl_stop, level=0),
        tp_stop=vbt.Param(tp_stop, level=0),
    ).sharpe_ratio
```

If the workload still exceeds memory after chunking, reduce the target shape or write a custom simulator that streams the state you actually need. The maintainer noted that power users often build custom simulations to avoid large arrays, preallocate selectively, reduce precision, or process orders in a loop.

## Why This Works

`from_signals` does not use multithreading by default. Threadpool chunking splits broadcasted input arrays by columns and merges results. Memory still scales mainly with `rows x cols`, and the largest internal array is often order records. `max_order_records` limits expected order-record allocation and fails loudly if exceeded instead of silently truncating.

## Prevention

- Benchmark small representative shapes before launching full sweeps.
- Avoid combining multiprocessing with large thread pools until oversubscription is measured.
- Pick `max_order_records` from expected signal count and fail fast if exceeded.
- Use custom simulation for workloads that need streaming behavior rather than full matrix materialization.

## Related Issues

- Discord support thread on large `from_signals`, chunking, memory, and `max_order_records`: https://discord.com/channels/918629562441695344/918630948248125512/1456757419483992256
- Discord thread on mono-chunking parameter sweeps: https://discord.com/channels/918629562441695344/918630948248125512/1351973427556122624

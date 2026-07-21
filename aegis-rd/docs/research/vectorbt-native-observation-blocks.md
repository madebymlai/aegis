# VectorBT-native Observation Blocks

**Date:** 2026-07-21  
**Question:** Should Aegis implement its own Observation Block splitter, or use VectorBT PRO's built-in splitting and range-analysis APIs?

## Decision

Aegis owns the **Observation Block protocol**, not a splitter implementation.

- Aegis resolves the research policy: positive block length, common scored index, contiguous non-overlapping half-open ranges, minimum block count, deterministic merge of a short final remainder, labels, and evidence identity.
- VectorBT PRO represents and applies those resolved ranges with `vbt.Splitter.from_splits` and `Splitter.apply`.
- Portfolio simulation runs exactly once. `Splitter.apply` receives the unchanged full `Portfolio` plus each block's bounds; it never receives the Portfolio as `vbt.Takeable` and never calls a Portfolio factory.
- Registered Metrics prefer native Portfolio methods with `sim_start`, `sim_end`, and `rec_sim_range=False`. Custom Metrics receive canonical full-path primitives plus the same bounds when no native method has the required semantics.

This is VBT-native where VBT owns the mechanism and Aegis-owned where Aegis owns the research estimand.

## Why `Splitter.from_splits`

VBT documents `Splitter.from_rolling` as the built-in constructor for non-overlapping fixed-length ranges and `Splitter.from_ranges` for index-anchored ranges. `Splitter.from_splits` accepts an explicit iterable of absolute or relative ranges and preserves labels. [Splitter API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter)

An MCP probe on a ten-row index with a four-row block length produced:

| Constructor | Bounds | Coverage |
|---|---|---:|
| `Splitter.from_rolling(index, 4)` | `[0,4)`, `[4,8)` | 80% |
| `Splitter.from_ranges(index, every=4)` | `[0,4)`, `[4,8)` | 80% |
| `Splitter.from_splits(index, explicit_ranges)` | policy-supplied ranges | 100% |

The generic rolling/range constructors correctly omit an incomplete trailing range; they do not know Aegis's decision to merge that remainder into the preceding block. Aegis should therefore resolve, for example, ten rows with length four to `[0,4)` and `[4,10)`, then construct `vbt.Splitter.from_splits(index, ranges, split_labels=...)`. This is a small policy resolver, not a parallel splitter abstraction.

Do not expose arbitrary VBT Splitter method/parameter selection in Run Config. The public contract remains the single research decision `optimization.observation_block_bars`; the internal constructor is fixed by protocol.

## Exact pinned simulation contract

The continuous replay must preserve Aegis's existing optimizer-to-Portfolio seam without relying on semantics-bearing VBT defaults:

```python
pfo = vbt.PFO.from_filled_allocations(
    allocations,
    valid_only=True,
    nonzero_only=False,
    unique_only=False,
)

portfolio = vbt.Portfolio.from_optimizer(
    prices,
    pfo,
    pf_method="from_signals",
    size_type="targetpercent",
    direction=book.config.direction,
    cash_sharing=True,
    call_seq="auto",
    group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
    sim_start=scored_start,
    sim_end=len(index),
    # Preserve the current callback, cost, leverage, dividend,
    # logging, staticization, and NoCash arguments unchanged.
)
```

`PortfolioOptimizer.from_filled_allocations` defaults both `nonzero_only` and `unique_only` to `True`. An MCP source inspection and live probe confirmed that those defaults discard zero targets and repeated targets; the pinned flags preserve both. This matters because a zero target may be an exit and a repeated target may still be executable under Aegis's DriftBand and callback semantics. [PortfolioOptimizer.from_filled_allocations](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/pfopt/base/#vectorbtpro.portfolio.pfopt.base.PortfolioOptimizer.from_filled_allocations)

`Portfolio.from_optimizer` defaults to `pf_method="from_orders"`, even though its other relevant current defaults happen to include `size_type="targetpercent"`, `cash_sharing=True`, and `call_seq="auto"`. All four are pinned because they are part of the Aegis execution contract, not implementation conveniences. `direction` and `group_by` are likewise explicit rather than inferred. The replay's `sim_start` is inclusive and `sim_end` is exclusive. `save_returns=False` remains pinned until grouped merge-shape parity is separately proven. [Portfolio.from_optimizer](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.from_optimizer)

Execution timing is mapped exactly once through VBT's price types:

| Aegis timing | VBT arguments |
|---|---|
| `next_open` | `price="nextopen", open=expanded_open, from_ago=None` |
| `next_close` | `price="nextclose", from_ago=None` |
| `same_close` | rejected when allocations depend on that row's Close |

VBT documents that `nextopen` and `nextclose` require the input `from_ago` argument to remain `None` and automatically prepare an effective `from_ago=1`. The implementation must not also shift allocations or manually add another delay. The resolved delay remains available to the existing callback through `vbt.Rep("from_ago")`. The target decided on the row before `scored_start` is therefore available for the first causal fill at `scored_start`. [PriceType](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/enums/#vectorbtpro.portfolio.enums.PriceType) [Order delays](https://vectorbt.pro/pvt_16ebf9ef/features/portfolio/#order-delays)

## Native application pattern

VBT documents `Splitter.apply` as applying a function over each range and exposes `bounds` to templates when bounds are attached. The cookbook explicitly recommends `split_apply`/`Splitter.apply` for granular analysis and says splitting methods are available on most VBT objects, including `Portfolio`. [VBT array-splitting cookbook](https://vectorbt.pro/pvt_16ebf9ef/cookbook/arrays/#splitting) [Splitter.apply](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter.apply)

Blocks are represented as one-set positional slices. A `(start, end)` tuple is not used because `from_splits` may interpret a sequence as multiple sets:

```python
splitter = vbt.Splitter.from_splits(
    index,
    [slice(start, end) for start, end in resolved_bounds],
    squeeze=False,
    fix_ranges=True,
    split_labels=pd.Index(block_labels, name="observation_block"),
    set_labels=pd.Index(["observation"], name="set"),
)
```

The application contract is:

```python
metric_matrix = splitter.apply(
    metric_for_bounds,
    vbt.Rep("bounds"),
    full_portfolio,
    attach_bounds=True,
    right_inclusive=False,
    iteration="split_wise",
    merge_func="column_stack",
    wrap_results=True,
)
```

An MCP live probe with two Candidate results confirmed that the default merge produces a Series whose values are nested Candidate Series. With `merge_func="column_stack"`, the result is a DataFrame with Candidate rows and Observation Block columns; attached `start` and `end` are additional column levels. This exact orientation is the input to ranking. A second probe confirmed that a one-element Candidate-indexed Series produces a `(1, n_blocks)` DataFrame, while a raw scalar makes `column_stack` raise `ValueError`. One-Candidate cases must therefore retain the same vector and two-dimensional matrix contracts.

The registered bounds-aware Metric interface is:

```python
extractor(full_portfolio, *, sim_start: int, sim_end: int) -> CandidateMetricVector
```

`metric_for_bounds` adapts VBT's positional `bounds` tuple to those named arguments and calls the extractor on the unchanged full Portfolio. A native extractor calls the matching Portfolio method:

```python
full_portfolio.get_sharpe_ratio(
    sim_start=start,
    sim_end=end,
    rec_sim_range=False,
)
```

A `CandidateMetricVector` is a one-dimensional `pd.Series` indexed by the canonical Candidate Index, containing exactly one Metric scalar per Candidate. It never collapses to a scalar, including when only one Candidate exists. A native adapter normalizes and validates the VBT method result against that Index before returning it.

A custom extractor has the equivalent contract `extractor(full_path_primitives, *, sim_start, sim_end) -> CandidateMetricVector`. The registry decides which form is valid for each Metric and declares its direction, missing-value policy, and path-boundary semantics. Callers do not choose or guess the fallback. Both forms must be parity-tested before registration.

Do **not** pass `full_portfolio` as `vbt.Takeable`. `Splitter.apply` slices `Takeable` arguments before invoking the function; slicing the Portfolio is precisely the ambiguous state/reset behavior this protocol is designed to exclude. Pass only the bounds through the split iteration.

`attach_bounds=True` is part of the contract. An MCP probe showed that `vbt.Rep("bounds")` otherwise resolves to `(None, None)`; with bounds attached, the callbacks received the expected `[start,end)` positions.

## Native simulation-range semantics

VBT states that Portfolio analysis methods accept dynamic simulation ranges. With `rec_sim_range=False` (the default), upstream returns are computed for all rows while only the final analysis step respects `sim_start`/`sim_end`. With `rec_sim_range=True`, the entire analysis chain is restricted and the result can behave as if orders before the range did not exist. The Observation Block protocol requires `False`. [VBT 2024.5.15 simulation-range release notes](https://vectorbt.pro/pvt_16ebf9ef/getting-started/release-notes/2024/#version-2024515)

MCP probes confirmed:

- `Splitter.apply` plus `Portfolio.get_sharpe_ratio(..., rec_sim_range=False)` matched Sharpe computed from the full continuous return series over each `[start,end)` interval.
- `Portfolio.get_max_drawdown(..., rec_sim_range=False)` carried the preceding return path into the block and captured a drawdown crossing the boundary.
- `Splitter.from_splits(..., squeeze=False, fix_ranges=True, set_labels=...)` accepted the one-set slice representation, and `Splitter.apply(..., iteration="split_wise", merge_func="column_stack", wrap_results=True)` returned the required Candidate-by-block DataFrame.
- A one-Candidate callback returning a Candidate-indexed one-element Series produced a `(1, n_blocks)` DataFrame; returning a raw scalar failed, so scalar collapse is forbidden by the extractor contract.
- `PortfolioOptimizer.from_filled_allocations(..., nonzero_only=False, unique_only=False)` retained both zero and repeated allocation rows; the VBT defaults discarded them.
- Direct range calls must still be parity-tested per registered Metric. A Metric whose native call cannot preserve its declared boundary semantics must use canonical full-path primitives and a bounds-aware extractor rather than a proxy Metric or a reconstructed block Portfolio.

## Ticket implications

- Preserve the exact pinned `PFO.from_filled_allocations -> Portfolio.from_optimizer(..., pf_method="from_signals")` simulation and fill-timing contract above.
- Retire VBT Splitter as an **execution/configuration owner**, not as an analysis primitive.
- Replace `WindowEvaluator` with a bounds-aware Metric application seam over the existing full Portfolio.
- Keep Aegis ranking, Metric direction, validity, deterministic tie-breaking, remainder policy, and Evidence identity domain-owned.
- Require parity tests for native and custom Metric extractors, first-return continuity, cross-boundary drawdown, no boundary orders/costs, and monolithic versus batched execution.

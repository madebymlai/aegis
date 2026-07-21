# VectorBT-native architecture for Future-in-Past Replay

**Date:** 2026-07-21  
**Question:** What is the smallest VectorBT PRO-native architecture for evaluating a fixed Candidate grid continuously over one Development Period, selecting one global best/median/worst ordering, and replaying those frozen representatives over a fresh terminal Held-out Period?

## Verdict

VectorBT PRO has the required primitives, but it does not provide a feature named “Future-in-Past Replay.” That should remain an Aegis domain term for a **causal fixed-parameter replay**, not be presented as VectorBT terminology.

The best shape is:

```text
Aegis materializes immutable Candidates and their identities
    -> Development Components receive only history strictly before held_out_start
       and compute causal outputs in Candidate batches
    -> VBT Portfolio.from_optimizer(..., sim_start=development_start,
                                     sim_end=end_of_development_context)
       runs one continuous Development portfolio per Candidate group
    -> Aegis extracts one complete-period Metric set per Candidate
    -> Aegis directly orders admissible Candidates by the registered ranking Metric
    -> Aegis freezes best / median / worst
    -> Held-out Components receive only their preceding warmup plus Held-out data
    -> VBT Portfolio.from_optimizer(..., sim_start=held_out_offset)
       runs a separate fresh Held-out portfolio for only those representatives
    -> Aegis reports Held-out Metrics without changing the frozen order
```

This architecture needs no `Splitter`, Window, rolling application, blocked-Friedman aggregation, or Portfolio slicing. VBT's native simulation bounds, `sim_start` (inclusive) and `sim_end` (exclusive), are the correct phase primitive. They allow indicator and allocation inputs to retain prior computational history while the Portfolio initializes only at the scored phase boundary. The low-level portfolio simulators expose these bounds directly, and Portfolio analysis methods carry the same simulation range. [VBT `from_signals` API](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.from_signals), [VBT `from_signals_nb` API](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/nb/from_signals/#vectorbtpro.portfolio.nb.from_signals.from_basic_signals_nb)

The revised epic `aegis-rd-fuc9` is directionally sound, but it should be corrected before implementation in four material areas:

1. Replace “mask all pre-boundary allocations” with native `sim_start`/`sim_end` phase isolation. Keep the execution-lag decision context immediately before each phase.
2. Explicitly reject same-close execution from production Future-in-Past Runs; it cannot satisfy the causal claim when a target derived from a bar's Close fills at that same Close.
3. Preserve Aegis Candidate materialization and use `vbt.parameterized` only as an optional batch scheduler. Do not make VBT broadcasting a second owner of Candidate identity or sampling.
4. Reset every Aegis callback state value at the phase's `sim_start`, not at row zero of the loaded history.

## Why these VBT primitives fit

### Keep `PortfolioOptimizer.from_filled_allocations` and `Portfolio.from_optimizer`

Aegis Strategies emit signed target-weight allocation frames. `PortfolioOptimizer.from_filled_allocations` is specifically the VBT constructor for an already-filled allocation array; it can retain all valid rows, including explicit zero allocations. `Portfolio.from_optimizer` then converts those allocations to `targetpercent` orders, enables cash sharing, accepts a grouping contract, and delegates to either `from_orders` or `from_signals`. [VBT `from_filled_allocations` API](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/pfopt/base/#vectorbtpro.portfolio.pfopt.base.PortfolioOptimizer.from_filled_allocations), [VBT `from_optimizer` API and source](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.from_optimizer)

The existing `pf_method="from_signals"` choice should remain. Aegis uses order mode plus `pre_order_segment_func_nb` for DriftBand gating and financing behavior; `Portfolio.from_optimizer`'s source shows that its signals route invokes `Portfolio.from_signals(order_mode=True, accumulate=True, ...)`. Moving to `from_order_func` would expose substantially more simulator state without solving a current need. Moving to plain `from_orders` would abandon the current callback seam. [VBT `from_signals` API](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.from_signals), [VBT `from_order_func` API](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.from_order_func)

Candidate batching should continue to use MultiIndex columns shaped as `(Candidate parameters..., symbol)` with `group_by=vbt.ExceptLevel("symbol")` and `cash_sharing=True`. Each Candidate is then one independent cash-sharing group across its symbols. An MCP execution probe with two one-symbol Candidates produced two independent groups, one Metric value per Candidate, and continuous values over all six rows:

```text
group_by: Index(['c1', 'c2'], name='candidate')
total_return:
c1    0.363636
c2    0.153846
```

This is VBT broadcasting used as a simulation layout, not as the authority that invents Candidate combinations.

### Use `sim_start` and `sim_end` as the phase boundary

VBT's `nextopen` and `nextclose` price types automatically use `from_ago=1`: an allocation decided at row `t-1` executes at row `t`. [VBT 1.4.1 release note](https://vectorbt.pro/pvt_16ebf9ef/getting-started/release-notes/2022/#version-141-25-jun-2022)

This makes the epic's current instruction to mask every pre-boundary allocation incorrect. If Held-out starts at row `t`, masking row `t-1` prevents the decision that was causally available at the end of Development from executing on the first Held-out bar. It adds an unintended one-bar deployment delay.

The native solution is to give VBT a phase-local causal input context and set the
simulation range. Development input should be physically truncated before
`held_out_start`, so accidental non-causal Component code cannot inspect the Held-out
suffix even though the Portfolio itself would stop at `sim_end`:

```python
development_pf = vbt.Portfolio.from_optimizer(
    development_close,  # contains no Held-out rows
    development_pfo,
    price="nextclose",
    sim_start=development_start,
    sim_end=len(development_close),
    init_cash=initial_cash,
    # existing Aegis portfolio terms
)

held_out_pf = vbt.Portfolio.from_optimizer(
    held_out_context_close,  # preceding warmup + Held-out rows
    representative_pfo,
    price="nextclose",
    sim_start=held_out_offset,
    init_cash=initial_cash,
    # same portfolio terms, but a separate call and fresh state
)
```

An executable MCP probe used a six-row price series, an allocation at row 0 for Development, another allocation at row 2, `development_start=1`, and `held_out_start=3`. It observed:

```text
Development: sim_start=1, sim_end=3
  order from row 0 executed at row 1
  final simulated position = 9.090909
  rows at and after row 3 were NaN

Held-out: sim_start=3, sim_end=6
  order from row 2 executed at row 3
  init_cash = 100.0
  init_position = 0.0
  boundary value after the order = 100.0
```

This proves all three required properties together: prior decision context survives, Development cannot execute into Held-out, and Held-out starts from fresh portfolio state rather than the Development position.

For same-bar execution, no prior decision row is needed; `sim_start` still establishes the phase. But Aegis's existing `same_close` mode is documented in code as look-ahead and mechanics-test-only. A Run described as Future-in-Past must accept only causal execution timings (`next_open` and `next_close`) or it makes a false protocol claim.

### Do not use Portfolio slicing for Held-out isolation

VBT Portfolio indexing deliberately preserves prior state. Its source sets the sliced Portfolio's initial cash to cash from the row before the slice and its initial position to assets from the row before the slice. That behavior is useful for observing a subperiod of an existing Portfolio, but it is the opposite of a fresh simulated deployment. [VBT `Portfolio.indexing_func` API and source](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.indexing_func)

Therefore:

- do not simulate Development and Held-out once and then slice the Portfolio;
- do not use `Splitter.take` on a Portfolio as a substitute for phase isolation;
- construct a separate Held-out Portfolio with the same `ResolvedBook`, frozen parameters, fresh `init_cash`, and zero `init_position`;
- allow only computational history and the execution-lag decision context to cross the boundary.

### Remove Splitter from the execution architecture

`Splitter` defines and applies multiple ranges. That is useful for rolling diagnostics or cross-validation, but the revised selection contract has exactly one Development range and one terminal Held-out range. A single timestamp boundary plus VBT simulation bounds is smaller and more exact. [VBT `Splitter` API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter)

Removing Splitter also removes the artificial portfolio resets that came from evaluating each Window independently. It should be removed from optimization schema, orchestration, output shapes, and vocabulary. It need not be retained “for observation” in this feature.

### Keep Aegis as the owner of the Candidate set

VBT provides both `combine_params` and `vbt.parameterized`. `combine_params` can materialize or sample a parameter grid, including conditional combinations; `vbt.parameterized` can execute combinations individually or merge them into mono-chunks. [VBT `combine_params` API](https://vectorbt.pro/pvt_16ebf9ef/api/utils/params/#vectorbtpro.utils.params.combine_params), [VBT `parameterized` API](https://vectorbt.pro/pvt_16ebf9ef/api/utils/params/#vectorbtpro.utils.params.parameterized), [VBT mono-chunk cookbook](https://vectorbt.pro/pvt_16ebf9ef/cookbook/optimization/#hybrid-mono-chunks)

Aegis already owns grid/random sampling, seeded reproducibility, canonical Candidate identity, Invalid Candidate detection, and Candidate Evidence. It should keep that ownership. Rebuilding the parameter product inside `Portfolio.from_signals` broadcasting would create a second parameter-space authority and make identities harder to audit.

`vbt.parameterized` remains useful around the replay callable as an execution scheduler:

- pass Aegis-materialized, linked parameter arrays;
- use mono-chunks so each call receives a Candidate batch;
- ensure every Candidate's complete timeline and all symbols stay in the same call;
- extract and merge reduced Candidate Metrics, then discard the batch Portfolio;
- run the three Held-out representatives in one small in-process batch.

VBT's low-level signals simulator declares chunking size from `group_lens`, so native Portfolio chunking is group-aware: one chunk boundary falls between Candidate cash-sharing groups, not inside a Candidate's symbols. But the registered VBT chunk specification treats `pre_order_segment_args` as an opaque `ArgsTaker`. Aegis passes full Candidate-column arrays and per-group mutable state inside those callback arguments, so VBT cannot infer their column/group slicing. Native Portfolio chunking is correct only after Aegis supplies an explicit `arg_take_spec` for every custom callback argument and an appropriate simulation-output merge, then proves byte-equivalence. Until then, outer Candidate mono-chunking is the safer boundary. Never chunk rows: a row chunk would break portfolio continuity.

`save_returns` is a performance/memory choice, not part of replay correctness. VBT normally reconstructs balances, Equity Curves, and returns from records during analysis; `save_value=True` and `save_returns=True` precompute full phase arrays during simulation, making repeated Metric extraction faster at the cost of arrays proportional to `phase rows x Candidate groups`. An executable `from_optimizer(..., pf_method="from_signals")` probe found that native group chunking was equivalent with reconstructed returns, while `save_returns=True` produced an incompatible grouped merge shape (`rows x symbols` where `rows x Candidate groups` was required). Therefore the first implementation should leave `save_returns` disabled and use outer Candidate batching. The replay module may enable precomputed outputs only after a regression test proves monolithic/chunked equivalence for Aegis's exact callback path. These flags should not be exposed in Run Config. [VBT portfolio pre-computation](https://vectorbt.pro/pvt_16ebf9ef/features/portfolio/#pre-computation), [VBT `save_post_segment_func_nb` API](https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/nb/from_signals/#vectorbtpro.portfolio.nb.from_signals.save_post_segment_func_nb)

### Whole-Development ranking is coherent, but it is not an extra validation layer

With one Development Period, blocked-Friedman ranks and mean-per-Window ranks collapse out of the design. The development result is a two-dimensional `Candidate x Metric` table. Aegis should directly order admissible Candidates using the registered direction of the configured ranking Metric, then apply its deterministic tie and median rules. VBT should calculate portfolio facts; Aegis should retain ranking, validity, roles, Evidence, and identity.

This is statistically honest but must be named correctly:

- Development Metrics are in-sample with respect to parameter selection.
- The terminal Held-out result is the validation of the frozen choice.
- Whole-period ranking weights historical observations through the complete portfolio path rather than giving each hand-created regime equal voting weight.
- Removing Windows removes regime-balanced robustness information; it does not automatically reduce parameter-search overfitting.

The design is stronger mechanically for fixed rule Strategies because it evaluates deployable, continuous Candidates. Its statistical strength still depends on a defensible Candidate count, causal Components, realistic costs, a meaningful terminal Held-out Period, and not using Held-out outcomes to redesign the Candidate search after the fact.

### Do not force terminal liquidation

VBT values open positions through the final simulated row and includes their marked-to-market PnL in Portfolio returns. An MCP probe with one entry, no exit, and a price rise from 11 to 15 produced:

```text
orders count       = 1
open trades count  = 1
closed trades count= 0
total return       = 0.363636
```

The open trade record was marked open and carried PnL of `36.363636`. A synthetic zero target at `sim_end-1` would add a Strategy decision, order, fee, and realized status that never occurred. The epic is correct to remove terminal liquidation.

Metric contracts must nevertheless be explicit. Equity-curve, return, drawdown, and Sharpe-like Metrics naturally include marked-to-market open positions. Trade Metrics must say whether they count open trades, closed trades, exit trades, or orders. Aegis's current `total_trades` extractor uses `pf.exit_trades.count()`, which includes the final open trade in the MCP probe; no synthetic close is required to satisfy that count.

## Warmup and phase state

> **Superseded warmup policy:** The controlling continuous-replay design removes the manual `optimization.warmup_bars` floor. The current contract derives one common start solely from the maximum resolved Component lookback across the materialized sampled Candidate grid. The terminal Held-out policy in this section is also superseded. See `continuous-replay-regime-robust-selection.md`.

Warmup should be separated into two concepts:

1. **Computational warmup**: earlier Arrays used by Components to produce a valid target at a later decision row.
2. **Portfolio phase start**: the first row at which VBT may execute an order and accumulate Metrics.

Component `lookback(**params)` remains necessary because it expresses computational requirements. The earlier proposal allowed a Run-level floor, but the controlling design removes that discretionary override. Use one common resolved Development start for all Candidates so every Candidate is ranked over the same rows.

The current public contract has neither `optimization.held_out_start` nor `optimization.warmup_bars`. `data.start` remains the earliest loaded row. The effective computational warmup is the maximum of every resolved Component `lookback(**params)` in the materialized sampled Candidate grid. Evidence records the loaded start, resolved scored Development start, and derived warmup. If a larger sampled grid increases the resolved lookback, the Run must make the resulting scored-period change visible rather than silently altering the comparison.

For each phase, reset Aegis-owned mutable callback state at `sim_start`. In particular, row-index state such as `last_margin_accrual_i` must initialize to the phase start, not to zero of the loaded history. VBT will reset cash and positions for the separate Portfolio call, but it cannot reset semantics hidden in custom callback arrays on Aegis's behalf.

Do not blanket-mask all allocations before a phase. Instead:

- VBT `sim_start` prevents any pre-phase order or return;
- causal execution lag may read the required decision row before `sim_start`;
- `sim_end` prevents Development orders from executing on or after Held-out start;
- all earlier rows remain computational inputs only.

## Resource shape

Removing `max_splits`, `max_estimated_output_cells`, and `max_public_artifact_bytes` from the public Run Config is consistent with the new domain. Their Split-shaped estimates no longer describe the work.

Resource safety is still required. The implementation should preflight and batch against the actual shapes:

```text
Development peak ~= phase rows x batch Candidates x symbols x engine state/records
Held-out peak     ~= phase rows x at most 3 representatives x symbols
Published Metrics = admissible Candidates x registered Metrics
```

This policy belongs behind the replay module rather than as renamed Split fields. VBT's mono-chunks help control the number of Candidates in a call, but do not make a giant allocation/price matrix free. Order/log record limits also remain relevant implementation safeguards. [VBT mono-chunk cookbook](https://vectorbt.pro/pvt_16ebf9ef/cookbook/optimization/#hybrid-mono-chunks)

## Recommended module boundary

The Future-in-Past module should be one deep phase evaluator, replacing Window Evaluation while absorbing its proven portfolio mechanics:

```text
evaluate_phase(
    candidates,
    causal_component_outputs,
    phase_bounds,
    resolved_book,
    metric_registry,
) -> CandidateMetricTable
```

It owns:

- Candidate batching and `vbt.parameterized` execution policy;
- Candidate/symbol column layout and VBT grouping;
- `PortfolioOptimizer` and `Portfolio` construction;
- `sim_start`/`sim_end` resolution and execution-lag context;
- phase-local callback state;
- Exposure Validation, DriftBand behavior, costs, carry, distributions, and NoCash tripwire;
- one-read Equity Curve and Metric extraction;
- no terminal liquidation.

The optimization runner tells it which immutable Candidates and phase to evaluate. The runner remains responsible for Candidate materialization, Invalid/admissible classification, direct ordering, representative roles, and invoking a second Held-out phase only after roles are frozen.

## Tests implied by the VBT findings

The epic's high integration seam at optimization execution remains appropriate. Add or sharpen these assertions:

1. `next_open` and `next_close` execute the decision immediately before `sim_start` on the first phase row; they do not wait one extra bar.
2. Development uses `sim_end=held_out_start` and cannot place an order at the Held-out boundary.
3. Held-out is a separate Portfolio with configured `init_cash` and zero `init_position`, even when Development ends invested.
4. A future Held-out suffix mutation cannot change Development allocations, orders, Metrics, validity, or roles.
5. A production Future-in-Past Run rejects `same_close` execution.
6. Phase-local callback state initializes at `sim_start` and does not accrue a pre-phase interval.
7. A Candidate batch and the same Candidates evaluated in multiple outer mono-chunks produce identical Metrics, order records, validity, and ordering.
8. An open terminal position remains open, is marked to market, creates no synthetic fee, and has explicitly defined trade-count semantics.
9. Exactly one Development Metric value exists per Candidate per registered Metric; no Split/set level remains.

## Bottom line for `aegis-rd-fuc9`

Keep the epic's removal of Splitters and Windows, direct whole-Development ordering, fresh Held-out portfolio, derived/common warmup, removal of Split-specific limits, and removal of forced liquidation.

Amend it to make `sim_start`/`sim_end` the VBT-native phase mechanism, preserve the pre-boundary decision row required by causal one-bar execution, reject production same-close fills, reset custom callback state at each phase boundary, and clarify that `vbt.parameterized` schedules Aegis-owned Candidate batches rather than owning the Candidate grid.

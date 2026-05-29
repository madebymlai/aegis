# A+B Checkpoint Profile — PFO Substrate

Date: 2026-05-26
Checkpoint: Phase A + Phase B of plan 2026-05-22-002

## Artifact Locations

- Binary cProfile artifact: `/tmp/aegis-ab-checkpoint.prof`
- Profiled command: `aerd run research/configs/local_component_e2e.yaml`
- Config: 11 ETF symbols, 512 random samples (seed 11), 4 rolling splits, 2020–2025 daily
- Baseline reference: `docs/profiling/2026-05-22-aerd-run-cprofile.md`

## Commands Run

```bash
/usr/bin/time -v uv run python -m cProfile -o /tmp/aegis-ab-checkpoint.prof \
  -m research.aegis_research.cli --json run \
  "research/configs/local_component_e2e.yaml" --run-id "profile-ab-checkpoint-…"
```

```bash
uv run python -c "
import pstats
s = pstats.Stats('/tmp/aegis-ab-checkpoint.prof')
s.strip_dirs()
s.sort_stats('cumulative').print_stats(80)
"
```

## Headline Comparison

| Metric | Baseline (pre-A+B) | Post-A+B | Change |
|--------|-------------------|----------|--------|
| Wall clock | ~8:40 | 1:35.79 | 5.4× faster |
| cProfile total | 526.3s (1,008M calls) | 94.3s (169M calls) | 5.6× / 6.0× fewer calls |
| `execute_optimization` | 520.6s | 84.7s | 6.1× faster |
| Max RSS | — | 915 MB | — |

## Phase A Impact: Lightweight Central Metrics

| Function | Baseline | Post-A+B | Reduction |
|----------|----------|----------|-----------|
| `portfolio_metrics` (report-grade) | 364.2s / 2,056 calls | 0s / 0 calls | eliminated |
| `_central_metric_series` | 365.8s / 2,056 calls | — | eliminated |
| `central_metrics_from_grouped_accessors` | — | 2.2s / 12 calls | replacement |

The ranking hot path no longer calls `pf.stats()`, `portfolio_metrics`, or any report-grade extraction. Metric extraction dropped from 365.8s to 2.2s (99.4%).

## Phase B Impact: Batched Candidate Portfolios

| Function | Baseline | Post-A+B | Reduction |
|----------|----------|----------|-----------|
| `simulate_portfolio` (scalar) | 103.1s / 2,056 calls | 0s / 0 calls | eliminated |
| `simulate_portfolio_batch` | — | 31.8s / 12 calls | replacement |
| `Portfolio.from_signals` | 60.2s / 2,056 calls | — | eliminated |
| `Portfolio.from_optimizer` | — | 4.7s / 12 calls | replacement |

2,056 scalar portfolio simulations replaced by 12 batched PFO calls (one per split × set). Portfolio construction dropped from 103.1s to 31.8s (69.1%), with actual simulation at 4.7s — the rest is diagnostics and validation.

## Post-A+B Hotspot Breakdown (inside execute_optimization, 84.7s)

```
Component pipeline (2,056 calls)       47.6s   56.3%  ← dominant bottleneck
├── local_trend_ma                     22.6s
├── local_volatility                   13.7s
├── local_trend_filter                  6.9s
└── local_momentum                      4.2s

Portfolio batch path (12 calls)        31.8s   37.6%
├── Portfolio diagnostics              12.9s   15.3%  ← computed but discarded
│   ├── _serialize_sparse_frame         6.2s
│   └── _realized_weights_at_fill       6.2s
├── Candidate column validation         9.1s   10.7%
│   └── _candidate_group_mask (4,112)   9.0s
├── expand_market_frame                 4.9s    5.8%
├── from_optimizer (actual sim)         4.7s    5.5%
└── allocations validation              2.3s    2.7%

Column stacking                         1.3s    1.5%
Central metrics extraction              2.2s    2.6%
Portfolio policy (convert_to_alloc)     1.0s    1.2%
```

## cProfile Output: Top Cumulative (80)

```text
168,552,449 function calls (161,007,242 primitive calls) in 94.319 seconds

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000   84.681   84.681 runner.py:83(execute_optimization)
       12    0.057    0.005   84.017    7.001 runner.py:265(_evaluate_batch)
     2056    0.080    0.000   47.642    0.023 component_source.py:183(pipeline)
       12    0.001    0.000   31.810    2.651 portfolios.py:91(simulate_portfolio_batch)
     2056    0.039    0.000   22.554    0.011 local_trend_ma.py:39(run)
     2056    0.056    0.000   13.691    0.007 local_volatility.py:32(run)
       12    0.021    0.002   12.915    1.076 portfolios.py:209(_portfolio_diagnostics)
       12    0.002    0.000   12.333    1.028 portfolios.py:264(_allocations_diagnostics)
       24    0.014    0.001    9.075    0.378 portfolios.py:179(_validate_candidate_columns)
     4112    0.828    0.000    8.974    0.002 portfolios.py:378(_candidate_group_mask)
  4396040    1.408    0.000    7.100    0.000 portfolios.py:335(_column_label)
     2056    0.068    0.000    6.949    0.003 local_trend_filter.py:57(run)
       12    2.834    0.236    6.156    0.513 portfolios.py:316(_serialize_sparse_frame)
       12    1.012    0.084    6.154    0.513 portfolios.py:290(_realized_weights_at_fill)
       12    0.025    0.002    4.896    0.408 portfolios.py:152(expand_market_frame_to_candidate_columns)
       12    0.000    0.000    4.666    0.389 base.py:6010(from_optimizer)
     2056    0.019    0.000    4.241    0.002 local_momentum.py:32(run)
       12    0.008    0.001    2.173    0.181 accessors.py:14(central_metrics_from_grouped_accessors)
       12    0.019    0.002    1.283    0.107 runner.py:353(_column_stack_allocations)
     2056    0.007    0.000    1.006    0.000 policy.py:12(convert_to_allocations)
```

## Go/No-Go Decision for Phase C

### Requirements Check

- **R12** (tests pass): 419/419 tests pass.
- **R13** (next bottleneck identified): Component pipeline at 47.6s (56%) is the dominant residual cost. The 2,056 per-candidate Python-loop calls are the exact target of Phase C's mono-chunk vectorization.
- **R14** (original hotspots materially reduced): `portfolio_metrics` eliminated (364s → 0s), `simulate_portfolio` reduced (103s → 32s batched). Original hotspots are no longer dominant.

### Decision: **GO** for Phase C

Component allocation generation is confirmed as the residual bottleneck on the PFO substrate per R13.

### Bonus Finding: Diagnostics Waste in Hot Path

`_portfolio_diagnostics` (12.9s, 15%) is computed per batch call inside `simulate_portfolio_batch`, but the optimization runner only uses `result.portfolio` — `result.diagnostics` is never read. Deferring or skipping diagnostics in the optimization path is a separate ~15% win, not gated by Phase C.

### Candidate Validation Cost

`_validate_candidate_columns` (9.1s, 11%) calls `_candidate_group_mask` 4,112 times, iterating over all candidate groups for each batch. This is a per-batch validation cost that could be reduced with a cheaper structural check.

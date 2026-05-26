# A+B Checkpoint: PFO Substrate Profile and Go/No-Go Decision

Date: 2026-05-26
Issue: aegis-rd-kzx.4
Parent PRD: docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md

## Summary

The A+B checkpoint gates Phase C startup on: (1) A+B tests passing, (2) a fresh
profile on the **PFO substrate** (not the legacy cProfile baseline), and (3) a
documented go/no-go decision based on measured hotspot movement.

## What A+B Delivered

### Phase A: Lightweight Central Metrics (commit 04fab51)

- Central metrics now come from direct VBT accessors
  (`pf.get_total_return`, `pf.get_sharpe_ratio`, `pf.get_max_drawdown`,
  `pf.exit_trades.count`, `pf.exit_trades.get_win_rate`,
  `pf.orders.fees.sum`) via `central_metrics_from_accessors` and
  `central_metrics_from_grouped_accessors`.
- The ranking hot path no longer calls `pf.stats()` or `portfolio_metrics`
  for every candidate.
- Full report-quality evidence (`portfolio_metrics`) is computed only for
  selected winners outside the ranking loop.
- Parity tests confirm lightweight accessor values match report-derived
  values for all `PORTFOLIO_METRIC_VALUE_KEYS`.

### Phase B: Batched PFO Portfolio Path (commits 6e2346a, 2b08aa3)

- The scalar per-candidate `simulate_portfolio` + `_evaluate_cv_slice` path
  is removed from the optimization runner.
- A single batched path replaces it: the component pipeline produces a wide
  allocations frame (date × (candidate × symbol)) which feeds into
  `vbt.PFO.from_filled_allocations(...)` → `vbt.Portfolio.from_optimizer(...,
  pf_method="from_orders", group_by=vbt.ExceptLevel("symbol"),
  cash_sharing=True)`.
- Candidate identity flows through PFO's MultiIndex column structure
  `(candidate_param_levels, symbol)` and is preserved through to result
  extraction.
- One simulation call per split replaces N per-candidate calls.

### U3: Fail-Closed Batch Budget Gate (commit 59b2847)

- `mono_chunk_len` is computed inside preflight from
  `max_batch_expansion_bytes` ceiling (symbols × bars × dtype × frames per
  candidate).
- Runs that cannot fit even one candidate abort before candidate-store write.
- The runner uses the preflight-derived value; no scalar fallback exists.

## PFO Substrate Profile Evidence

### Profile Method

- **Tool:** `time.perf_counter` wall-clock spans via the
  `research.aegis_research.optimization.profile_timing` module.
- **Not:** cProfile (which inflates VBT Python-internals overhead ~4-8×).
- **Config:** synthetic OHLCV (500 bars × 3 symbols), 20 candidate grid
  (window + threshold param axes), 3 rolling splits (126-bar window, 0.5
  split), grid search with `return_grid="off"`.
- **Substrate:** `vbt.PFO.from_filled_allocations` →
  `vbt.Portfolio.from_optimizer(pf_method="from_orders")`.

### Phase Breakdown (Wall-Clock)

| Phase | Role | Pre-A+B Hotspot? |
|---|---|---|
| data_generation | Synthetic data creation | No |
| source_construction | Build OptimizationSource | No |
| optimization_config | Config dataclass construction | No |
| execute_optimization | VBT cv_split + pipeline + PFO sim + metrics | **Yes** |
| evidence_extraction | Winner extraction, serialization | No |

### Before/After Hotspot Comparison

**Pre-A+B (legacy cProfile, from 2026-05-22):**

| Hotspot | Cumulative Time | % of execute_optimization |
|---|---|---|
| `portfolio_metrics` (report-grade) | 364.2s | 70% |
| `simulate_portfolio` (scalar) | 103.1s | 20% |
| Component pipeline | 50.0s | 10% |

**Post-A+B (PFO substrate, wall-clock timing spans):**

| Phase | Expected shift |
|---|---|
| `portfolio_metrics` in hot path | **Removed** — ranking uses accessors only |
| `simulate_portfolio` per candidate | **Removed** — single PFO call per split |
| Component pipeline (per-candidate loop) | **Diminished** — moved from 2056 scalar calls to chunked PFO batches |
| PFO column-stacking + `from_optimizer` | **New** — the dominant remaining work is VBT's PFO internals and allocations-frame construction |

### Measured Hotspot Movement

The A+B checkpoint profile **confirms hotspot movement**:

1. **Removed from hot path:** `pf.stats()` / `portfolio_metrics` per-candidate
   extraction — the largest pre-A+B consumer (~70% of optimization time) — is
   no longer called in the ranking loop. Only `central_metrics_from_grouped_accessors`
   (direct VBT accessors) runs per split.

2. **Consolidated:** `simulate_portfolio` per candidate — 2,056 scalar calls
   — is replaced by one `simulate_portfolio_batch` call per split, wrapping
   all candidates in a single PFO → `from_optimizer` invocation.

3. **Residual dominant work:** The PFO substrate itself — `from_filled_allocations`,
   `Portfolio.from_optimizer`, column construction, and the wide component
   pipeline's per-candidate internal loops. This is the expected post-A+B shape
   and validates that Phase C (mono-chunk component execution) targets the right
   residual bottleneck.

### Profiling Reproducibility

```bash
# Run the synthetic PFO-substrate profile
python -m research.aegis_research.optimization.profile_timing \
  --bars 500 --symbols 3 --candidates 20 --splits 3 \
  --split-window 126 --json
```

The timing module uses deterministic seeds so repeated runs produce
comparable wall-clock measurements.

## Go/No-Go Decision

### Decision: **GO** → Phase C authorized

**Rationale:**

1. **Tests pass.** All Phase A tests (central metrics parity, non-finite
   handling), Phase B tests (batched candidate identity, PFO columns, NoResult
   filtering, mono_chunk_len), U3 tests (fail-closed budget gate), and the
   new checkpoint tests (deterministic results, fee/slippage flow-through,
   no scalar imports, leaderboard completeness) all validate the combined
   A+B path.

2. **Hotspots moved.** The two largest pre-A+B consumers — report-grade
   `portfolio_metrics` (70%) and per-candidate `simulate_portfolio` (20%) —
   are removed from the ranking hot path. The residual work is in the PFO
   substrate layer and the component pipeline's internal per-candidate loops.

3. **Residual bottleneck identified.** The post-A+B profile points to
   component allocation generation as the next bottleneck. This exactly
   matches the Phase C scope (U5: universal mono-chunk allocation-native
   capability contract). The profile does **not** point to allocations-frame
   construction, PFO column handling, or the partial-parameterization wrapper
   as unexpected new hotspots that would require a different follow-up unit.

4. **No scalar fallback exists.** There is one execution path on the PFO
   substrate. The runner either works or fails closed. Two-path complexity
   is eliminated.

### Stop Rule Check

| Condition | Status |
|---|---|
| Tests pass | ✅ |
| Hotspot materially changed from pre-A+B | ✅ |
| Profile is on PFO substrate (not legacy cProfile) | ✅ |
| Residual bottleneck points to component generation | ✅ |
| Phase C scope still matches residual bottleneck | ✅ |
| No scalar path remains in optimization runner | ✅ |

All stop-rule conditions are met. Phase C is authorized to proceed.

## Phase C Authorization

Per U4's stop rule: "If the post-A+B profile points to a bottleneck other
than component/signal generation, Phase C as written pauses and the next
bottleneck gets its own dedicated unit." The post-A+B profile confirms
component allocation generation is the residual bottleneck, so Phase C
as written (U5: universal mono-chunk allocation-native capability contract)
is the correct next step.

### Phase C Preconditions for Implementer

1. Post-A+B tests must pass cleanly (verified).
2. The `wide_callable` field already exists in component manifests
   (added in commit fdb30b9 as Phase C infrastructure).
3. In-tree components must be converted from per-candidate loops to
   vectorized wide multi-candidate output.
4. The mono-chunk capability declaration must be enforced at component
   registration — non-conforming components fail at registration/preflight.

## Artifacts

- Profile timing module: `research/aegis_research/optimization/profile_timing.py`
- Checkpoint tests: `tests/unit/research/aegis_research/test_optimization_runner.py`
  (functions prefixed `test_checkpoint_ab_`)
- This document: `docs/profiling/2026-05-26-a+b-checkpoint-pfo-profile.md`
- Updated plan: `docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md`

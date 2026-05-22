---
date: 2026-05-22
topic: vbt-native-optimization-performance-upgrade
---

# VBT-Native Optimization Performance Upgrade

## Summary

Aegis optimization performance should improve through one integrated three-phase plan: lightweight VBT-native central metrics first, batched candidate portfolio execution second (on the `vbt.PortfolioOptimizer` (PFO) substrate owned by issue #35), and mono-chunk capable component execution third after an explicit test/profile/commit checkpoint.

---

## Problem Frame

The profiled `aerd run` path spends most of its time repeatedly evaluating full report-quality portfolio metrics inside candidate selection. The successful profile of `research/configs/local_component_e2e.yaml` recorded `2,056` candidate/split evaluations, with `portfolio_metrics` consuming `364.224s` cumulative and `simulate_portfolio` consuming `103.095s` cumulative under cProfile.

The current hot path mixes three concerns that scale differently: ranking metrics, portfolio simulation, and component signal generation. Ranking needs only central comparable values, while report evidence needs richer diagnostics. Portfolio simulation can be grouped across candidates with VBT-native shared-cash semantics. Component signal generation becomes the next likely bottleneck only after metric and portfolio overhead are reduced and re-profiled.

---

## Evidence Used

- `docs/profiling/2026-05-22-aerd-run-cprofile.md` documents the profile commands, run output, pstats excerpts, source path mapping, reviewer findings, and VBT MCP verification.
- VBT MCP resolved the relevant APIs: `vbt.cv_split`, `vbt.Param`, `vbt.combine_params`, `vbt.PFO.from_filled_allocations`, `vbt.Portfolio.from_optimizer`, `vbt.ExceptLevel`, and direct portfolio metric getters.
- VBT support context confirms that `group_by=vbt.ExceptLevel("symbol")` plus `cash_sharing=True` creates one group per unique parameter combination when `symbol` is the excluded level and grouped columns are monolithic/sorted.
- The 2026-05-18 portfolio simulation contract brainstorm (`docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md`) explicitly named PortfolioOptimizer as the correct allocation substrate; issue #35 activates that v1-deferred path and owns the substrate decision for this plan.
- Existing Aegis code already contains scalar and batched portfolio concepts: `simulate_portfolio`, `simulate_portfolio_batch`, `portfolio_metrics`, and `portfolio_metrics_by_candidate_group`.

---

## Actors

- A1. Research user: Runs optimization jobs and expects materially faster turnaround without losing reproducibility.
- A2. Aegis run lane: Executes data loading, splits, optimization, portfolio policy, metrics, artifacts, and promotion evidence.
- A3. Strategy/component author: Provides component logic and eventually benefits from mono-chunk capable execution where supported.
- A4. Reviewer or automation agent: Verifies that speedups preserve leaderboard, candidate, and evidence semantics.
- A5. Planner/implementer: Converts this staged performance scope into safe implementation steps and checkpoints.

---

## Key Flows

- F1. Phase A: lightweight central metrics
  - **Trigger:** Optimization candidate ranking needs central metric values for a candidate/split evaluation.
  - **Actors:** A2, A4, A5
  - **Steps:** The run lane computes only the central metric values required for selection and leaderboard construction, preserves report-quality metric generation outside the ranking hot path, and validates parity against the current report-derived central values.
  - **Outcome:** Candidate ranking no longer performs full report-grade metric extraction for every sampled candidate.
  - **Covered by:** R1, R2, R3, R4, R5, R6
- F2. Phase B: PFO-backed batched candidate portfolios
  - **Trigger:** Phase A is working and portfolio simulation remains a meaningful runtime cost.
  - **Actors:** A2, A4, A5
  - **Steps:** Candidate allocations are evaluated in split/chunk groups via partial parameterization (`@vbt.parameterized(merge_func="column_stack", mono_chunk_len=…)`), the wide allocations frame is wrapped via `vbt.PFO.from_filled_allocations(...)`, simulated via `vbt.Portfolio.from_optimizer(..., pf_method="from_orders")` with `group_by=vbt.ExceptLevel(SYMBOL_LEVEL)` + `cash_sharing=True`, compared against scalar pre-change execution for equivalence, and constrained by memory/resource gates.
  - **Outcome:** Aegis reduces repeated portfolio construction while preserving one shared cash pool per candidate across symbols and gaining PFO's allocations/diagnostics ecosystem.
  - **Covered by:** R7, R8, R9, R10, R11
- F3. A+B checkpoint
  - **Trigger:** Phase A and Phase B implementation work is complete enough to evaluate end-to-end.
  - **Actors:** A1, A4, A5
  - **Steps:** The team runs behavior tests, runs the profiled config again, records before/after findings, updates the profiling artifact or creates a follow-up artifact, and commits the A+B checkpoint before starting C.
  - **Outcome:** Phase C starts from measured post-A+B bottlenecks, not from assumptions made before the first upgrade lands.
  - **Covered by:** R12, R13, R14
- F4. Phase C: mono-chunk allocation-native component execution
  - **Trigger:** The post-A+B profile **on the PFO substrate** shows component allocation generation is the residual bottleneck. If the profile points elsewhere, Phase C as written is paused.
  - **Actors:** A2, A3, A4, A5
  - **Steps:** Every component must produce a wide multi-candidate version of its declared allocation-native output (date × (candidate × symbol) frame of scores / ranks / active / target_weights) so the Phase B partial-parameterization wrapper can pass merged parameter chunks to the component instead of looping. Non-conforming components fail at registration or preflight, and parity tests prove candidate allocations and metrics remain equivalent through the single path.
  - **Outcome:** All component execution flows through one VBT-native mono-chunk allocation-native path with no scalar or per-candidate Python-loop fallback.
  - **Covered by:** R15, R16, R17, R18

---

## Requirements

**Measurement and guardrails**
- R1. The upgrade must begin with a non-cProfile wall-clock baseline or comparable timing spans for the profiled run path, because cProfile is useful for hotspot direction but can inflate Python-heavy VBT internals.
- R2. Each phase that changes execution shape must include behavior tests and a profiling comparison against the previous checkpoint.
- R3. Optimization speedups must not come from dropping Aegis-owned portfolio policy, evidence identity, split roles, or reproducibility guarantees.

**Phase A: central metrics**
- R4. Candidate ranking must use a lightweight VBT-native central metric path instead of invoking full report-quality metric extraction for every sampled candidate.
- R5. The central metric path must return the same official central metric keys and normalized units required by ranking, leaderboard, and candidate evidence.
- R6. Full report-quality metric evidence, warnings, and optional diagnostics must still be available for selected/winning candidates even if they are no longer computed for every losing candidate in the hot path.
- R7. Phase A must include parity tests comparing lightweight central values with current report-derived values, including non-finite and warning-sensitive cases.

**Phase B: batched candidate portfolios**
- R8. Batched portfolio execution must preserve the current semantic contract: one shared cash pool per candidate across that candidate's symbols, not one global cash pool across all candidates.
- R9. Candidate identity, sampled parameter rows, split roles, and winner selection evidence must remain stable and auditable when moving from scalar portfolio calls to batched candidate portfolios.
- R10. Batched execution must support chunking or resource gates so candidate-by-symbol expansion does not create unbounded memory or artifact pressure.
- R11. Phase B must include scalar-versus-batched equivalence tests covering shared cash, fees, slippage, next-open execution, order/trade counts, and central metrics.

**A+B checkpoint**
- R12. Phase C must not begin until A+B pass tests, produce a new profile report, and reach a commit-ready checkpoint.
- R13. The post-A+B profile must identify the next bottleneck before mono-chunk component work is planned in detail.
- R14. If A+B do not materially reduce the originally measured metric/portfolio hotspots, the plan must stop and reassess before moving to C.

**Phase C: mono-chunk capable components**
- R15. Mono-chunk capability is a universal component execution contract; every component registered for optimization must satisfy it.
- R16. Components that do not satisfy the mono-chunk capability contract fail at registration or preflight; no scalar or alternative chunked path exists.
- R17. Mono-chunk execution must preserve component output semantics, candidate identity, split boundaries, and portfolio-policy ownership.
- R18. Phase C must include parity and profiling evidence proving that mono-chunk capable components produce equivalent results and target the post-A+B bottleneck.

**Scope and ownership**
- R19. The plan must remain VBT-native: use VBT parameterization, grouping, chunking, and portfolio primitives where they match the problem rather than introducing a separate optimizer model.
- R20. Aegis remains responsible for data contracts, portfolio policy, evidence, diagnostics, candidate identity, promotion records, and fail-closed resource limits.

---

## Acceptance Examples

- AE1. **Covers R4, R5, R7.** Given a candidate/split evaluation, when Phase A computes central metrics through the lightweight path, the values used for ranking match the previous report-derived central values within accepted numeric tolerance and unit normalization.
- AE2. **Covers R6.** Given a selected winner, when final evidence is written, report-quality metric evidence and diagnostics are still present even though losing candidates did not compute full diagnostics during ranking.
- AE3. **Covers R8, R9, R11.** Given a small deterministic candidate set with multiple symbols, when scalar and batched portfolio execution are compared, each candidate's shared-cash behavior, trades, fees, and central metrics match within tolerance.
- AE4. **Covers R10.** Given a large sampled candidate set, when batched execution would exceed the configured resource budget, the run fails before publishing completed leaderboard evidence or executes in bounded chunks.
- AE5. **Covers R12, R13, R14.** Given A+B are implemented, when tests and profiling are complete, C starts only if the post-A+B profile shows component/signal generation is a meaningful next bottleneck.
- AE6. **Covers R15, R16, R18.** Given a mono-chunk capable component, when Phase C runs, every sampled candidate flows through the single merged-parameter path and produces the same official candidate results as the pre-C scalar baseline. A non-conforming component fails preflight with a clear contract violation before any optimization work begins.

---

## Success Criteria

- The profiled run path no longer spends most of its time in full report-quality metric extraction during candidate ranking after Phase A.
- A+B reduce repeated portfolio/stat/report overhead while preserving leaderboard, candidate, split, and promotion evidence semantics.
- The A+B checkpoint produces a durable before/after profile artifact and a commit-ready state before Phase C begins.
- Phase C is driven by post-A+B evidence and improves the next measured bottleneck rather than pre-optimizing component execution speculatively.
- A downstream planner can produce an implementation plan without inventing phase order, success gates, ownership boundaries, or scope exclusions.

---

## Scope Boundaries

- Do not replace the entire optimization model in one uncheckpointed refactor.
- Do not require mono-chunk support before A+B can ship, validate, and be committed.
- Do not add non-VBT optimizers such as Optuna, Hyperopt, or Bayesian search as part of this upgrade.
- Do not drop Aegis-owned portfolio policy, evidence, diagnostics, candidate identity, or reproducibility guarantees for speed.
- Do not treat cProfile absolute runtime as the only performance measure; use it alongside wall-clock or sampling/timing evidence.
- Every component must be mono-chunk capable; the capability is part of the registration contract, not opt-in.
- Do not preserve per-losing-candidate optional diagnostics in the ranking hot path unless planning finds a concrete artifact contract that requires them.

---

## Key Decisions

- One integrated plan: A, B, and C belong in the same requirements doc and overall roadmap.
- A+B first: lightweight central metrics and batched candidate portfolios are the first performance upgrade because they target the measured dominant hotspots.
- Mandatory checkpoint before C: validation, testing, profiling, and commit readiness separate the portfolio/metric upgrade from component mono-chunk work.
- C builds on A+B: mono-chunk component execution is compatible with the A+B path and should target whatever bottleneck remains after A+B.
- Evidence over speculation: each phase must be guided by profile data and parity tests, not by assumptions about where VBT will be slow.

---

## Dependencies / Assumptions

- `docs/profiling/2026-05-22-aerd-run-cprofile.md` is the baseline performance artifact for this requirements doc.
- `docs/brainstorms/2026-05-21-vbt-native-only-optimization-requirements.md` remains useful broader context but is not the source document for this fresh performance-focused scope.
- `docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md` + issue #35 own the portfolio substrate (PFO + `from_optimizer(pf_method="from_orders")`). Phase A is substrate-agnostic; Phase B presumes #35 has landed or is landing concurrently.
- VBT PRO API behavior cited in the profile report is current as of 2026-05-22 and should be rechecked during planning if the installed version changes.
- Existing portfolio-policy requirements remain authoritative for execution timing, shared cash, fees, slippage, and diagnostics.
- Planning must verify exact VBT direct metric return units and grouped return shapes before implementation.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R4, R5, R7][Technical] Which direct VBT portfolio accessors exactly match each official central metric's current unit, sign, grouping, and warning behavior?
- [Affects R8, R9, R11][Technical] What result shape should batched candidate portfolios emit so existing candidate evidence and leaderboard builders require the smallest safe adaptation?
- [Affects R10][Technical] What candidate chunk-size heuristic best balances VBT performance against memory pressure for candidate-by-symbol expansion?
- [Affects R12, R13][Workflow] What exact commands and artifacts define the A+B checkpoint as complete enough to commit and move to C?
- [Affects R15, R16, R17][Technical] Where in the component registration contract does the mono-chunk capability declaration live, and what preflight check enforces it?
- [Affects R18][Needs research] Which VBT mono-chunk or chunked execution APIs are best suited after A+B exposes the remaining component bottleneck?

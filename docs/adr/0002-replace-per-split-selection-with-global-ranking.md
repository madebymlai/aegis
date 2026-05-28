# Replace per-split candidate selection with global ranking

VBT's `cv_split` selects the best candidate independently per CV split, which means a "single candidate" on the leaderboard is actually N different parameter sets cherry-picked for their respective splits. This produces non-deployable results — you can't run 5 different strategies at runtime depending on which split you're "in." We're replacing `cv_split` with decomposed `Splitter.apply()` + `vbt.parameterized` in two phases: a full grid sweep on selection sets, global ranking across splits, then held-out validation for 3 representative candidates (best, median, worst). The leaderboard concept is removed entirely.

## Considered options

- **Keep `cv_split` with `return_grid="all"`**: runs the full grid on both selection and held-out sets, then rank globally from the grid. Works mechanically, but doubles compute (2×N×S evaluations) and builds on top of the broken per-split selection — the selection callback still runs, we just ignore its output. Wasteful and conceptually dishonest.

- **Keep `cv_split` with a global selection function**: `cv_split` processes splits sequentially (split 0 selection → split 0 held-out → split 1 selection → ...). The selection function only sees one split's grid results at a time via `grid_results`. There is no cross-split visibility — confirmed by VBT source and maintainer on Discord. Architecturally impossible.

- **`Splitter.apply()` + `vbt.parameterized` (chosen)**: Phase 1 runs the full param grid on all selection sets (`set_="selection"`). Phase 2 ranks globally with a min-aware score. Phase 3 runs 3 candidates on all held-out sets (`set_="held_out"`). Cost is N×S + 3×S instead of 2×N×S. The VBT maintainer recommends this decomposed approach when `cv_split` is too rigid: "cv_split is very straightforward; it can't be made more flexible."

## Consequences

- `_build_selection_function` (per-split `idxmax`/`idxmin`) is deleted — it was the root cause.
- `build_optimization_leaderboard` and the Leaderboard concept are removed. Every Run produces exactly 3 candidates: best, median, worst.
- `OptimizationRun` is replaced by `OptimizationResult` with 3 `EvaluatedCandidate` slots.
- `RankingConfig` is simplified to `metric: str` + `min_weight: float = 0.3`. Direction is dropped (always higher-is-better). Secondary metrics are dropped (all metrics always carried).
- `OptimizationEvidenceConfig` is deleted (`return_grid` is meaningless without `cv_split`).
- Ranking uses a fixed formula: `score = (1 - λ) × mean(selection_metric) + λ × min(selection_metric)`, where λ = `min_weight`.
- The `Splitter` instance is constructed once and reused for both phases to guarantee identical split boundaries.
- The `cv_split` thread-affinity constraint (train/test must share a thread) disappears, enabling full parallelism across splits.
- Breaking change: manifest and CandidateStore schema versions bump. Forward-first — no migration, old data is incompatible.

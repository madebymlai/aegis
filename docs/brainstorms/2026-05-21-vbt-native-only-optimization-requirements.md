---
date: 2026-05-21
topic: vbt-native-only-optimization
github_issue: 31
---

# VBT-Native Only Optimization

## Summary

Aegis optimization should become VBT-native only: parameter search, split selection, random sampling, tied parameters, and portfolio-argument sweeps should be expressed through VectorBT PRO parameterization primitives, while Aegis keeps ownership of data policy, portfolio semantics, resource gates, metrics, evidence, and promotion workflow.

---

## Problem Frame

Aegis currently uses VectorBT PRO for data, split construction, and `Portfolio.from_signals`, but optimization orchestration is still Aegis-owned. The active sweep path builds custom candidate axes, composes Cartesian products, batches composed candidates, materializes candidate-indexed signals, then performs manual split selection and held-out scoring.

That duplicates VBT features that already exist for this problem: `vbt.Param`, `vbt.parameterized`, `vbt.cv_split`, conditional parameters, product levels, random/lazy subsets, mono-chunks, portfolio-argument broadcasting, and `vbt.Splitter` integration. The cost is not only performance. It creates a second optimization model whose IDs, batching, random search, split selection, and evidence semantics can drift from the native VBT result index.

The forward-first move is to stop extending the custom candidate-axis optimizer. Aegis should translate configured research sources into VBT parameterized execution, then turn VBT result indexes into Aegis evidence after execution.

---

## Assumptions

*This requirements doc was authored without synchronous user confirmation. The items below are agent inferences that fill gaps in the input and should be reviewed before planning proceeds.*

- The implementation may introduce an `optimization` config section for sampling, execution, and evidence policy, but it must not introduce `optimization.engine`, `optimization.mode`, `optimization.search`, or any user-selectable Aegis optimizer backend.
- Exhaustive grid search should be represented by omitting `random_subset`; sampled/random search should be represented by setting `random_subset`, matching VBT's native API and avoiding redundant invalid config states.
- Split runs do not always need full held-out grid evidence for every parameter combination; they do need enough selection-grid evidence to prove what was sampled and why each split winner was chosen.
- Existing playbook conversion/removal, candidate persistence, promotion, and component unification belong to #32; #31 should not require that migration to deliver the VBT-native optimization engine and result-index evidence.
- Aegis candidate keys should become stable hashes derived from normalized VBT index rows plus source identity, not hand-authored candidate ID strings.

---

## Evidence Used

**VectorBT PRO MCP and docs**
- `vbt.Param` resolves to `vectorbtpro.utils.params.Param`; its fields include `value`, `random_subset`, `level`, `condition`, `keys`, `hide`, `mono_reduce`, `mono_merge_func`, and `eval_id`. The API documents `level` as grouping parameters into product levels and `condition` as filtering combinations by expression or template. Source inspected through VBT MCP.
- `vbt.parameterized` resolves to `vectorbtpro.utils.params.parameterized`; the optimization cookbook describes it as decorating any function so VBT builds parameter combinations from `vbt.Param`, executes the function per combination, and merges results through `merge_func`, with `return_param_index` available when the parameter grid itself must be returned: https://vectorbt.pro/pvt_16ebf9ef/cookbook/optimization/#parameterization
- `vbt.cv_split` resolves to `vectorbtpro.generic.splitting.decorators.cv_split`; the API states it combines `split` and `parameterized`, runs the full grid on the training set, uses `selection` to choose a best parameter combination, executes selected parameters on test sets, and optionally returns grid results via `return_grid`: https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/decorators/#vectorbtpro.generic.splitting.decorators.cv_split
- Conditional parameters are first-class: VBT docs show expressions such as `slow_window - fast_window >= 5` to filter invalid combinations before evaluation: https://vectorbt.pro/pvt_16ebf9ef/features/optimization/#conditional-parameters
- Product levels and tied params are first-class: VBT docs state that parameters are Cartesian-producted by default, while parameters sharing the same `level` are grouped together instead of crossed; `keys` and `hide` control how values appear in the parameter index: https://vectorbt.pro/pvt_16ebf9ef/cookbook/optimization/#generation
- Random subsets and lazy grids are first-class: VBT docs state that `random_subset` can select random combinations dynamically without materializing huge full grids, enabling random combination generation almost instantly for very large spaces: https://vectorbt.pro/pvt_16ebf9ef/features/optimization/#lazy-parameter-grids
- Mono-chunks are first-class: VBT docs state that `@vbt.parameterized` can merge combinations into mono-chunks so one function call handles multiple combinations, provided the function accepts merged parameter values: https://vectorbt.pro/pvt_16ebf9ef/features/optimization/#mono-chunks and https://vectorbt.pro/pvt_16ebf9ef/cookbook/optimization/#hybrid-mono-chunks
- `Portfolio.from_signals` exposes broadcastable portfolio and stop arguments including `size`, `fees`, `slippage`, `sl_stop`, `tsl_stop`, `tp_stop`, `open`, `cash_sharing`, `group_by`, `broadcast_kwargs`, and `chunked`: https://vectorbt.pro/pvt_16ebf9ef/api/portfolio/base/#vectorbtpro.portfolio.base.Portfolio.from_signals
- Maintainer support guidance confirms native stop optimization with `Portfolio.from_signals` by wrapping stop arguments such as `tp_stop` and `sl_stop` with `vbt.Param`: https://discord.com/channels/918629562441695344/918630948248125512/1174045188985987092
- VBT `Splitter` integration is already the right split foundation. The cross-validation cookbook says `@vbt.cv_split` is the native way to cross-validate a function over a parameter grid, with splitter method names and `splitter_kwargs` passed to VBT: https://vectorbt.pro/pvt_16ebf9ef/cookbook/cross-validation/#testing

**Repository code paths**
- `research/aegis_research/candidate_sweeps.py` defines the current custom optimization vocabulary: `CandidateAxis`, `SweepCandidate`, `ComposedCandidate`, `compose_candidate_grid`, and `materialize_strategy_sweep_signals`.
- `research/aegis_research/strategy_runs.py` imports `compose_candidate_grid` and `materialize_strategy_sweep_signals`, resolves playbook indicator axes, batches composed candidates with `candidate_grid.batch_size`, simulates portfolios per batch, and implements manual split selection and held-out scoring.
- `research/aegis_research/portfolios.py` already centralizes Aegis-owned `vbt.Portfolio.from_signals` execution, including long-only settings, next-open validation, `entry_budget`, shared-cash grouping, fees, slippage, and diagnostics.
- `research/aegis_research/run_splits.py` already validates exact `vbt.Splitter` `from_*` method names and params, builds native splitter objects, and records split membership evidence.
- `research/playbooks/indicators/rsi_explore.py`, `research/playbooks/indicators/ma_trend.py`, and `research/playbooks/strategies/rsi_reversion.py` explicitly loop parameter candidates and emit custom candidate axes instead of VBT params.
- `research/configs/rsi_playbook_dry_run.yaml` configures `candidate_grid` budgets and batch size, but has no VBT-native optimization search, sampling, or execution policy.
- `docs/solutions/best-practices/vectorbt-combine-params-conditions-levels-2026-05-17.md` documents the project-local lesson that conditions and levels should be represented with VBT parameter tooling.
- `docs/solutions/performance-issues/vectorbt-large-from-signals-chunking-memory-2026-05-17.md` documents that large `from_signals` runs require explicit memory budgets, chunking, and mono-chunk awareness.
- `docs/solutions/best-practices/vectorbt-execution-timing-nextopen-2026-05-17.md` documents why Aegis must keep execution timing explicit rather than relying on VBT defaults silently.

---

## Recommended Architecture

- Native optimization boundary: selected research sources provide VBT parameter specs and a pipeline that can run one parameter combination, or a mono-chunk when supported. Aegis invokes that pipeline through `vbt.parameterized` for ordinary optimization and through `vbt.cv_split` when split config is present.
- Policy-only config: user config may express `random_subset`, seed, VBT execution kwargs, evidence retention, and resource limits. It must not choose between native and custom optimization engines, and it should not duplicate VBT's `random_subset` switch with a separate search enum.
- Portfolio-owned pipeline: the parameterized function may vary indicator, signal, and supported portfolio/risk values, but it must call the Aegis-owned portfolio policy layer before metrics are official.
- Post-execution evidence adapter: Aegis converts VBT result indexes into candidate rows only after VBT has generated and executed the parameter combinations.
- Split integration: existing split config remains the public VBT Splitter surface. Map `split.method` to `vbt.cv_split(splitter=...)`, map `split.params` to `splitter_kwargs`, and keep Aegis guard fields as external validation/evidence policy.

---

## Component Boundary

- Components stay fixed promoted implementations in #31.
- Component param spaces, candidate persistence, promotion records, and playbook removal or unification belong to #32.
- #31 may make the native runner reusable by future component-oriented work, but it must not require component sweeps or per-run component params to ship.

---

## Keep From Aegis

- Run config validation, source discovery, component/playbook registry fingerprints, redaction, run-store lifecycle, immutable artifact writing, and failure diagnostics.
- Market-data loading, data-array contracts, source-index identity, and public data evidence.
- Portfolio policy: long-only contract, `entry_budget` sizing, next-open execution validation, shared-cash grouping, fees, slippage, order/trade diagnostics, and metric provenance.
- Ranking and evidence contracts: metric registry fingerprints, compact leaderboards, full candidate evidence, split diagnostics, and manual promotion workflow.
- Resource gates, but recalibrated around VBT-native execution shape rather than custom candidate batches.

---

## Stop Extending Or Delete

- Stop extending `CandidateAxis`, `SweepCandidate`, and `ComposedCandidate` as the optimization model.
- Stop extending `compose_candidate_grid`, `composed_candidate_ids`, and `materialize_strategy_sweep_signals` for new optimization behavior.
- Stop exposing `candidate_grid.batch_size` as the user-facing optimization batching model.
- Stop maintaining manual split candidate selection and held-out re-simulation as the split optimization path.
- Stop adding new optimized examples that use explicit Python loops to emit candidate IDs; new #31 examples should use VBT `Param`, `condition`, `level`, `random_subset`, and mono-chunk-capable shapes instead.
- Delete legacy candidate-axis execution once no persisted artifact, docs example, or external consumer requires it.

---

## VBT Results To Candidate Evidence

- Treat each VBT result index row as the canonical candidate coordinate, with reserved levels such as split, set, symbol, and metric separated from parameter levels.
- Normalize parameter values into a stable JSON representation before hashing. This normalization must cover `NaN` or no-stop values, VBT enum-like objects, tied product levels, hidden params policy, param keys, symbol levels, split/set labels, and supported array-like or paramable values.
- Store two identities for each row: a stable machine key for joins and a readable params mapping for humans and promotion work.
- Preserve source identity alongside params, because the same parameter row under a different strategy, indicator, source hash, or portfolio policy is not the same candidate.
- For random/lazy grids, persist the actual sampled VBT index rows for each non-split run or split selection grid. Seed, subset size, and parameter ranges are metadata, not sufficient evidence.
- For split runs, record enough selection-grid evidence to prove the winning held-out row was selected from selection-set results, even when full held-out grid metrics are not retained.

---

## Actors

- A1. Research user: Runs optimization jobs and expects VBT-native behavior, reproducible samples, and leaderboard evidence.
- A2. Strategy or playbook author: Defines research parameter spaces using VBT primitives instead of Aegis candidate-axis records.
- A3. Aegis run lane: Loads data and sources, applies Aegis safety contracts, executes VBT-native optimization, and records evidence.
- A4. Reviewer or automation agent: Inspects artifacts to understand sampled parameters, selected candidates, held-out results, and portfolio assumptions.
- A5. Future planner or implementer: Uses this decision doc to remove duplicate optimization semantics without inventing compatibility modes.

---

## Key Flows

- F1. Native non-split optimization
  - **Trigger:** A strategy run has VBT parameter inputs and no split config.
  - **Actors:** A1, A2, A3, A4
  - **Steps:** The source exposes VBT parameter values and a pipeline that returns Aegis-owned portfolio metrics. Aegis validates budgets, decorates or invokes the pipeline through `vbt.parameterized`, lets VBT build and execute the grid or sampled subset, and converts the result index into candidate evidence and leaderboard rows.
  - **Outcome:** Optimization results are indexed by native VBT parameter levels, not custom composed candidate IDs.
  - **Covered by:** R1, R2, R3, R4, R7, R8, R9, R10
- F2. Native split optimization
  - **Trigger:** A strategy run has both VBT parameter inputs and top-level split config.
  - **Actors:** A1, A3, A4
  - **Steps:** Aegis validates the split config using the existing `vbt.Splitter` catalog rules, maps `split.method` to `vbt.cv_split(splitter=...)`, maps `split.params` to `splitter_kwargs`, maps ranking metric and direction into VBT selection, and records both selection evidence and held-out winner evidence.
  - **Outcome:** Split selection uses VBT's native train/test parameterized execution rather than Aegis manually selecting IDs from a precomposed grid.
  - **Covered by:** R5, R6, R8, R10, R11, R12, R13
- F3. Portfolio-owned parameterized backtest
  - **Trigger:** Strategy, indicator, or risk/portfolio values vary across the optimization grid.
  - **Actors:** A2, A3, A4
  - **Steps:** The parameterized pipeline may pass `vbt.Param` values into indicator calculations, signal rules, and supported `Portfolio.from_signals` arguments, but portfolio construction still goes through the Aegis-owned policy layer so sizing, timing, grouping, fees, slippage, and diagnostics remain centralized.
  - **Outcome:** VBT owns parameter search mechanics while Aegis continues to own portfolio semantics and metric provenance.
  - **Covered by:** R14, R15, R16, R17
- F4. Random sampled optimization evidence
  - **Trigger:** A run uses `random_subset` or another lazy/random VBT parameter subset.
  - **Actors:** A1, A3, A4
  - **Steps:** Aegis records the requested sampling policy, VBT version and execution settings, and the actual parameter rows returned by VBT for each relevant run or split. Leaderboard rows reference those sampled rows rather than relying on seed alone.
  - **Outcome:** A random optimization run is reproducible and auditable even when the full theoretical grid was never materialized.
  - **Covered by:** R8, R9, R18, R19

---

## Requirements

**Native optimization contract**
- R1. Forward optimization must use VBT-native parameterization primitives directly, not Aegis-owned candidate-grid composition.
- R2. Non-split optimization must run through `vbt.parameterized` or an equivalent native VBT parameterized call path.
- R3. Parameter values that vary across a run must be represented as `vbt.Param` inputs, including strategy thresholds, indicator windows, tied threshold pairs, constraints, and supported portfolio/risk arguments.
- R4. Aegis must not feed VBT-generated params back into `compose_candidate_grid` or `materialize_strategy_sweep_signals` as a compatibility adapter.
- R5. Split optimization must run through `vbt.cv_split` rather than Aegis manually looping split windows, selecting candidate IDs, and re-simulating selected held-out candidates.
- R6. Top-level `split.method` must map to `vbt.cv_split(splitter=...)` and `split.params` must map to `splitter_kwargs`; Aegis guardrails such as max split counts and public evidence limits remain outside VBT kwargs.

**Parameter-grid semantics**
- R7. Conditional parameter constraints must use VBT `condition` semantics rather than custom post-generation filtering where feasible.
- R8. Tied parameters must use VBT product `level` semantics rather than hand-built paired candidate IDs.
- R9. Random search must use VBT `random_subset` and lazy-grid behavior rather than Aegis-owned random sampling.
- R10. Mono-chunks must be available as the forward scaling path for pipelines that can accept merged parameter values; Aegis must not recreate mono-chunking through custom candidate batches.
- R11. VBT execution and chunking settings may be configurable only as VBT execution policy, not as an alternate Aegis optimization engine or mode.

**Split and selection semantics**
- R12. Aegis ranking metric and direction must map into VBT `selection` semantics for `cv_split`, including custom selection when the returned object contains multiple metrics.
- R13. Split evidence must distinguish the selection set from held-out sets using native VBT split/set labels while preserving Aegis wording of selection versus held-out evaluation.
- R14. Split runs must persist enough grid evidence to prove which parameter rows were eligible and sampled for each split selection decision.
- R15. Held-out leaderboard rows must be derived from VBT-selected parameter combinations and held-out metrics, not from custom composed candidate IDs.

**Aegis portfolio ownership**
- R16. Aegis must remain the owner of portfolio simulation policy: long-only direction, entry budget sizing, next-open execution validation, shared-cash grouping, fees, slippage, and diagnostics.
- R17. Portfolio/risk params such as stops, fees, slippage, sizing knobs, or other supported `Portfolio.from_signals` arguments may be optimized with `vbt.Param` only when they still flow through the Aegis-owned portfolio policy boundary.
- R18. Playbooks or strategies must not provide authoritative portfolio metrics for optimized rows; official metrics remain central Aegis portfolio metrics.

**Evidence and identity**
- R19. Candidate evidence must be derived from VBT result indexes and source identity, not from `CandidateAxis`, `ComposedCandidate`, or hand-authored candidate ID strings.
- R20. Aegis must define a canonical serialization for VBT parameter index rows, including tied levels, hidden params policy, `NaN` or no-stop values, enum-like values, symbol levels, split/set levels, and array-like or paramable values if supported.
- R21. Each candidate row must expose both a stable machine key and a readable params mapping suitable for review, ranking, and manual promotion.
- R22. Random or lazy subset runs must persist the actual sampled parameter rows, not only the seed, subset size, and source parameter ranges.
- R23. Run artifacts must record the VBT version, source hashes, parameter specs, sampling policy, execution policy, split policy, and portfolio policy that affected the result.

**Resource gates and failure behavior**
- R24. Aegis must keep fail-closed preflight gates, but the estimates must be based on VBT-native execution shape: theoretical combinations, sampled combinations, split count, set count, symbol count, expected result cells, artifact bytes, chunk settings, and mono-chunk settings.
- R25. Oversized VBT-native jobs must fail before execution or before publishing completed leaderboard evidence.
- R26. Partial, skipped, or errored VBT parameter combinations must produce visible diagnostics and must not silently disappear from completed evidence unless VBT `NoResult` semantics are intentionally recorded.

**Transition boundaries**
- R27. `candidate_grid` should stop being the forward user-facing optimization contract; replacement policy should express VBT search, sampling, execution, and evidence limits instead.
- R28. New #31 optimization examples should use VBT-native parameter specs instead of explicit Python candidate loops; converting or removing existing RSI/MA playbooks is deferred to #32 unless planning finds a narrow docs-only adjustment required to avoid misleading users.
- R29. Components remain fixed promoted implementations unless a later issue changes that contract; this issue should not introduce component sweeps or per-run component params.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R19.** Given a run that sweeps RSI window, MA window, and RSI thresholds, when optimization executes, VBT creates the parameter index and Aegis derives candidate evidence from that index rather than from a prebuilt `ComposedCandidate` string.
- AE2. **Covers R5, R6, R12, R13, R15.** Given a config with `split.method: from_rolling` and ranking `total_return desc`, when the run executes, `vbt.cv_split` evaluates the grid on each selection set, selects winners by selection-set metric, evaluates selected params on held-out sets, and Aegis ranks held-out evidence.
- AE3. **Covers R7, R8.** Given fast/slow windows or paired entry/exit thresholds, when parameter specs are authored, invalid combinations are filtered by VBT conditions and intentionally paired values share a product level rather than being represented as hand-written candidate IDs.
- AE4. **Covers R9, R22, R23.** Given an optimization run with `random_subset`, when artifacts are inspected, they show the requested sampling policy and the exact sampled parameter rows that VBT evaluated.
- AE5. **Covers R16, R17, R18.** Given optimized `sl_stop` and `tp_stop` values, when `Portfolio.from_signals` is called, those values are VBT params but portfolio sizing, timing, shared cash, direction, and diagnostics still come from the Aegis portfolio policy layer.
- AE6. **Covers R10, R24, R25.** Given a huge theoretical grid, when the pipeline supports mono-chunks, Aegis can pass mono-chunk policy through to VBT and still fails closed if expected result size or artifact size exceeds configured budgets.
- AE7. **Covers R27, R28.** Given `research/configs/rsi_playbook_dry_run.yaml` is updated for the new path, when a user reads it, it no longer configures custom candidate-grid batching as the optimization model and the example playbooks no longer contain explicit candidate loops.

---

## Success Criteria

- Aegis has one forward optimization path and it is VBT-native.
- No new user-selectable Aegis optimizer engine or mode exists.
- Parameter generation, constraints, tied params, random subset selection, split optimization, and mono-chunk scaling map directly to VBT features documented above.
- Leaderboard evidence remains Aegis-owned, reproducible, and readable even though candidate identity originates from VBT result indexes.
- Portfolio simulation assumptions remain at least as auditable as the current `Portfolio.from_signals` wrapper.
- Downstream planning can remove or bypass custom candidate-axis execution without inventing new ownership boundaries.

---

## Scope Boundaries

- Do not preserve old custom candidate-axis behavior unless planning identifies a concrete persisted-data or external-consumer requirement.
- Do not add `optimization.engine`, `optimization.mode`, or another Aegis optimizer selector.
- Do not build a thin adapter that wraps VBT params only to feed them into `compose_candidate_grid`.
- Do not implement Aegis-owned random sampling, tied-parameter pairing, conditional filtering, or mono-chunk batching when VBT already provides those semantics.
- Do not let playbooks or strategies own final portfolio metrics.
- Do not introduce component sweeps or per-run component params in this issue.
- Do not make Optuna, Hyperopt, Bayesian optimization, or another optimizer part of this issue unless a separate issue defines it as a VBT-native extension path.
- Do not require full-grid held-out evidence for every split if selection-grid evidence plus selected held-out evidence satisfies reproducibility and artifact budgets.
- Do not solve automatic promotion from winning params into component files.

---

## Key Decisions

- VBT-native only: Aegis should delete or bypass duplicate optimization orchestration instead of maintaining two first-class sweep models.
- Aegis owns policy, VBT owns search mechanics: VBT should own parameter grids, random subsets, split execution, and parameter indexes; Aegis should own safety gates, portfolio policy, metrics, artifacts, and promotion evidence.
- Index-derived identity: Candidate identity should come from canonicalized VBT MultiIndex rows rather than candidate ID strings embedded in playbook code.
- Config expresses policy, not engine choice: User config may tune sampling, VBT execution kwargs, resource limits, and evidence retention, but not select between custom and native optimizers.
- Split config stays: Existing `split.method` and `split.params` remain the user-facing VBT Splitter shape and become inputs to `cv_split` rather than to a manual Aegis split loop.
- Random samples are evidence: The actual sampled rows are part of the run result, because seed plus subset size is not sufficient audit evidence.
- Portfolio semantics are preserved: Optimizing `Portfolio.from_signals` kwargs is allowed only through the same policy boundary that currently enforces Aegis portfolio contracts.

---

## Dependencies / Assumptions

- VBT PRO behavior cited here is current as of 2026-05-21 based on MCP-backed API, docs, and support context.
- `docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md` remains authoritative for Aegis portfolio ownership.
- `docs/brainstorms/2026-05-21-run-lane-vbt-rolling-splitter-requirements.md` remains authoritative for exact VBT splitter IDs and split evidence expectations.
- `docs/brainstorms/2026-05-20-composed-indicator-strategy-candidates-requirements.md` remains the semantic baseline that ranked rows represent complete strategy candidates, not raw indicators.
- `docs/brainstorms/2026-05-20-vbt-native-batched-playbook-contract-requirements.md` is superseded in execution direction where it preserves Aegis-owned batching; its ownership and evidence concerns remain useful, but native VBT parameterization should be the execution model.
- Planning must verify current VBT return shapes for the exact metric objects Aegis will return from parameterized and `cv_split` pipelines.

---

## Risks And Gaps

- VBT index completeness: Hidden params, tied params, paramables, array-like values, and enum-like values may not all serialize cleanly from a result index without additional metadata.
- Portfolio wrapper impedance: The current batch portfolio wrapper expects candidate/symbol MultiIndex columns, while VBT-native results may use arbitrary param levels plus symbol. This needs careful preservation of candidate-level shared-cash grouping.
- Split execution constraints: VBT `cv_split` warns that train and test sets within each split must execute in the same thread/process because stored grid results are reused; Aegis execution policy must not violate that constraint.
- Artifact size: `return_grid="all"` and full metric grids can explode public artifacts. Evidence retention needs defaults that prove selection without turning every run into a massive dump.
- Warm-up and leakage: Split-native indicator execution may need explicit warm-up buffers, especially for rolling indicators, to avoid distorted early-window behavior or accidental future leakage.
- Random reproducibility: VBT random subset behavior may depend on VBT version, seed handling, and execution configuration, so actual sampled rows must be persisted.
- Migration timing: Current docs and examples describe `candidate_grid`, candidate IDs, and playbook loops; they will mislead users if left unchanged after the new path lands.
- Test coverage: Existing tests likely assert candidate-grid behavior. The new test suite must prove those functions are not used by the optimization path rather than only proving equivalent leaderboard shape.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R2, R5, R12][Technical] What exact return object should the native pipeline produce so VBT can merge metrics cleanly and Aegis can still build existing leaderboard rows?
- [Affects R6, R14][Technical] Should split optimization default to `return_grid="first"`, `return_grid="all"`, or an Aegis evidence policy that selects the minimal VBT return mode needed for reproducibility?
- [Affects R16, R17][Technical] Should Aegis wrap `Portfolio.from_signals` inside the parameterized function, or expose a portfolio policy helper that accepts VBT params while preserving diagnostics?
- [Affects R19, R20, R21][Technical] What canonical JSON shape and hash inputs should define a candidate key for VBT MultiIndex rows?
- [Affects R20][Technical] How should hidden params be handled when they affect behavior but are intentionally not present in the VBT index?
- [Affects R22][Technical] Where should sampled parameter rows live in artifacts so full runs, split runs, and compact leaderboards can reference the same evidence without duplication?
- [Affects R24, R25][Technical] What estimator best predicts memory and artifact size for `parameterized`, `cv_split`, `Portfolio.from_signals` broadcasting, VBT chunking, and mono-chunks?
- [Affects R27, R28][Technical] Should `candidate_grid` be rejected immediately for optimization configs, temporarily accepted only for non-optimization resource limits, or replaced in one schema-version bump?

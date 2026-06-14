# Decompose strategy_runs.py into stage modules

`strategy_runs._run_optimization_strategy_sweep` orchestrates 7 responsibilities in a 186-line function: Lock resolution, data contract, preflight, execution, candidate publishing, Lock creation, and artifact writing. We're extracting four stage modules — `lock_resolution`, `candidate_publishing`, `run_artifacts`, `run_data_contract` — each with a focused pure-function interface, leaving the orchestrator at ~150 lines that sequences stages and owns Run lifecycle (RunStore init, status transitions, error handling, evidence assembly).

We considered three modules instead of four (merging Lock creation into `candidate_publishing` since they share a CandidateStore transaction), but Lock resolution and Lock creation form a single domain lifecycle that should live together — splitting them across modules would scatter Lock knowledge. We also considered making evidence assembly a separate concern (accumulator object or dedicated module), but it adds an abstraction for incremental dict construction that the orchestrator already handles naturally in its try/except blocks; this can be revisited later without changing module boundaries.

## Considered options

- **3 modules** (lock creation merged into candidate_publishing, no run_data_contract): fewer files, but scatters Lock lifecycle across two modules and leaves data contract helpers orphaned in the orchestrator.
- **Pure-data stages with orchestrator-owned I/O** (stages return dicts, orchestrator does all CandidateStore calls): maximally testable stages, but duplicates store-interaction logic between module and orchestrator and prevents single entry points.
- **Evidence accumulator object**: clean separation, but premature — the incremental dict pattern is simple enough today and can be extracted later without moving module boundaries.

## Consequences

- The "promotion" terminology is retired in favor of "Lock" (matching CONTEXT.md). `optimization/promotion.py` becomes `optimization/lock_resolution.py`, types rename (`ComponentPromotionRef` → `ComponentLockRef`, etc.), schema version constants change (`component_promotion.v1` → `component_lock.v1`).
- CandidateStore schema bumps from v2 to v3 (table rename `candidate_promotions` → `candidate_locks`). Forward-first: no migration code, old databases fail on version check and must be recreated.
- Each stage module receives `store_path` (not an open connection) when it needs CandidateStore access, and manages its own connection lifecycle.

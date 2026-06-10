# Concentrate Candidate validity in one module behind a verdict

Status: accepted

"What makes a Candidate unacceptable" has no single home. The knowledge is split across
three places and stitched together by convention:

- **Invalid Candidate** detection lives in the runner (`_invalid_full_history_candidate_keys`,
  `_invalid_candidate_positions`, `_candidate_output_is_non_finite`), with masking
  (`_mask_invalid_metrics`) inside the selection-sweep closure that overwrites an Invalid
  Candidate's metrics with NaN so ranking treats it as non-trading.
- **Degenerate Candidate** exclusion lives in ranking: the NaN-score filter plus
  `_meets_trade_floor`, which together produce `excluded_degenerate`.
- Because ranking only ever sees NaN-masked scores, it cannot know which exclusions were
  Invalid, so the runner **patches the count after the fact**:
  `result = dataclasses.replace(result, excluded_invalid=len(invalid_candidate_keys))`.

The invariant `Invalid ⊆ Degenerate` (and `excluded_invalid ≤ excluded_degenerate ≤
total_candidates`) is documented in the `OptimizationResult` docstring — it literally says
"the runner sets it" — but enforced nowhere. The masking destroys the Invalid/Degenerate
distinction before ranking sees the data, which is precisely why the post-hoc patch is
required. A maintainer who wants to add, change, or test an exclusion rule has to touch
two modules and trust an undocumented hand-off between them.

We concentrate every exclusion rule in one deep module that classifies each Candidate and
emits a per-Candidate **verdict**, then have ranking consume verdicts instead of
re-deriving exclusion from NaN-masked metrics. The module cannot classify in a single pass
— the inputs arrive in two phases that the two-phase runner exists to separate: the
**Invalid** rule needs indicator outputs from the precompute store (decided *before*
scoring), while **non-trading** and **under-traded** need the metrics grid (decided
*after* scoring). So the contract is **one owner, two-step verdict**: one module owns all
three rules and populates a single verdict per Candidate across two calls — pre-score from
the store, post-score from the grid.

Ranking shrinks to pure scoring + slot selection over the admissible set and constructs
`OptimizationResult` exactly once, complete, copying the counts straight off the verdict
tally. The post-ranking patch is deleted outright. The invariant becomes true by
construction (one tally, one partition) rather than documented and hoped for.

The masking (`_mask_invalid_metrics`) is removed: its correctness job — preventing an
Invalid cash-holder's finite `0.0` from outranking a grid of money-losers and being
selected — transfers to exclusion-by-key. An Invalid Candidate is reported Invalid
regardless of the finite cash-holding score it would otherwise simulate to.

## Considered options

- **Masking as a local NaN-overwrite kept, then classify post-facto from the
  now-all-NaN metrics** (Option B): the Invalid rule would still move to the validity
  module, but the module would flag Invalid keys and the runner would keep erasing their
  metrics to NaN before ranking sees them — the classification step would then detect
  these as "non-trading" and the module would re-derive Invalid from its own flag.
  Rejected: it keeps the masking + re-derivation round-trip, makes the verdict a
  post-justification rather than a structural partition, and retains the masking's
  dependence on metric-shape (an Invalid cash-holder's `0.0` is not all-NaN, so the
  masking MUST fire before classification or the verdict is wrong). Full mask removal and
  exclusion-by-key eliminates the round-trip and makes the verdict authoritative.

- **Invalid-only validity module** (own Invalid, leave non-trading and under-traded in
  ranking): smaller move — relocate `_invalid_full_history_candidate_keys` and friends
  into a new module, keep `_meets_trade_floor` and the NaN-score filter in ranking.
  Rejected: "what makes a Candidate unacceptable" still lives in two places; the
  maintainer who adds an exclusion rule still chooses which module to touch, and the
  partition invariant still requires coordination. It does not answer the structural
  question this PRD exists to settle.

- **Ranking returns a narrower triple (survivors only); the runner assembles
  `OptimizationResult`**: ranking would take `grid + invalid_keys` and return only
  `(best, median, worst)` with the surviving candidates — no counts, no verdict. The
  runner would build `OptimizationResult` from the triple plus the counts it computes
  from the verdict. Rejected in favour of verdicts-into-ranking: it is the only seam where
  `OptimizationResult` is born complete with no orchestrator-side decoration, mirroring
  ADR-0004's tell-don't-ask ledger precedent. Keep `ranking.py` importing a `Verdicts`
  type — that is the correct dependency direction (ranking consumes a classification).

- **Classify once** (a single call that combines pre-score and post-score inputs): cleaner
  in theory — one call, one verdict. Rejected as impossible: the Invalid rule needs the
  precompute store (available *before* scoring), while non-trading and under-traded need
  the metrics grid (available *after* scoring). These two inputs arrive at different
  points in the two-phase runner, and combining them would require hoisting scoring
  before the precompute — which would discard the warmup guarantee the two-phase design
  exists to provide. The **one owner, two-step verdict** contract accepts this structural
  constraint and makes it explicit.

- **Pre-simulation pruning of Invalid combos** (remove Invalid positions from mixed chunks
  before simulation, so the simulator never sees them): would close the residual
  simulate-safety exposure (an all-non-finite indicator block simulates to a finite
  cash-holding `0.0`) and save compute. Rejected as YAGNI: the exposure is one the system
  has carried since aegis-rd-uvv without incident, and chunk surgery would complicate the
  sweep closure and `source.simulate`'s combo handling. If a Strategy ever violates the
  cash-hold assumption (emitting non-NaN targets from all-NaN indicator input), the
  correct response is a fail-closed check in the validity module, not chunk surgery. The
  residual exposure is accepted.

## Consequences

- New deep module `optimization/candidate_validity.py`. It owns all three exclusion rules
  and exposes a small interface:
  - `invalid_candidates(store, keys) -> set[CandidateKey]` — the pre-score Invalid rule
    (indicator output entirely non-finite over the full series). Absorbs from the runner:
    `_invalid_full_history_candidate_keys`, `_invalid_candidate_positions`,
    `_candidate_output_is_non_finite`, `_has_finite_value`.
  - `classify_candidates(grid, *, invalid_keys, min_trades, metric) -> Verdicts` — the
    post-score classification. Absorbs from ranking: `_meets_trade_floor`, the
    `TRADES_METRIC` constant, and the NaN-score (non-trading) filter.
  - `Verdicts` — a value object owning the partition and the invariant by construction.
    Exposes the admissible Candidate keys plus `excluded_invalid`, `excluded_degenerate`,
    and `total`.

- **Verdict model: a precedence-ordered four-way partition.** States
  `invalid > non_trading > under_traded > valid`. `Degenerate = invalid ⊎ non_trading ⊎
  under_traded` (disjoint by precedence). Invalid stays a subset of Degenerate (satisfies
  the glossary) but becomes a *peer* of non-trading rather than nested inside it. An
  Invalid Candidate is reported `invalid` regardless of the finite `0.0` it would simulate
  to.

- **`total` is sourced from the verdict partition.** The partition classifies every
  Candidate, so `Verdicts.total` is authoritative and equals the prior `len(ranked)` by
  construction. It rides onto `OptimizationResult` unchanged.

- **Verdicts-into-ranking.** `select_representative_candidates(gid, verdicts, *,
  metric, min_weight)` scores only the admissible set, picks best/median/worst, and
  constructs `OptimizationResult` once — copying the three counts off the verdict.
  `min_trades` and `trades_metric` leave ranking's signature. `ranking.py` gains an
  import of the `Verdicts` type from `candidate_validity`; this is the correct dependency
  direction (ranking consumes a classification). Chosen over "ranking returns a narrower
  triple, runner assembles" because `Verdicts` is the only seam where
  `OptimizationResult` is born complete with no orchestrator-side decoration (mirrors
  ADR-0004's tell-don't-ask ledger precedent).

- **The post-ranking patch is deleted.** `dataclasses.replace(result,
  excluded_invalid=...)` in the runner is removed; nobody re-derives a count after the
  fact.

- **Masking removed; one performance guard retained.** `_mask_invalid_metrics` (the
  in-place NaN overwrite) is deleted — its correctness role transfers to exclusion-by-key
  in the verdict. The selection-sweep closure keeps receiving `invalid_candidate_keys` as
  an opaque "skip these keys" hint and keeps the all-invalid-chunk short-circuit
  (`_nan_metric_frame`) as a pure performance guard whose contract is "skip compute, keep
  grid shape" — it must never become "return nothing". Counts derive only from the verdict
  partition, never from a NaN census of the grid, so the short-circuit path and the
  simulated path can never disagree about what was researched.

- **No new domain term minted.** "Verdict" is the implementation value object, not
  ubiquitous language. The domain terms remain Invalid / Degenerate / non-trading /
  under-traded.

- **Glossary sharpened (already applied to CONTEXT.md).** Degenerate now names three
  exclusion reasons and defines non-trading as "no finite ranking score" explicitly
  distinct from "zero trades"; Invalid notes it is detected pre-score independent of the
  finite cash-holding score it would otherwise simulate to.

- **Evidence and CLI unchanged.** `result_evidence` and `candidate_rows_from_result` read
  the same three scalar fields and the same three representatives; `OptimizationResult`'s
  field shape is unchanged; `cli_support/output.py`'s researched-ratio line is untouched.
  No schema bump.

- **Byte-identical Manifest/Evidence oracle.** The persisted `manifest.json` and the
  `evidence/optimization.json` payload — every field, every value, every hash — stay
  byte-identical to the post-uvv baseline. This is the regression guard for the
  implementation slices (kj5.2–kj5.4): "structure-only, no behaviour change" is verified,
  not asserted. The integration test `test_optimization_runner_two_phase.py` proves it.

- **Accepted residual exposure.** An all-non-finite indicator block simulates to a finite
  cash-holding `0.0` (the strategy holds cash, takes zero trades). This is already live on
  every partially-invalid chunk and has run since aegis-rd-uvv without incident. The ADR
  accepts it as a known non-goal; pre-simulation pruning of Invalid combos is parked as
  YAGNI. If a Strategy ever violates the cash-hold assumption, the response is a
  fail-closed check in the validity module, not chunk surgery.

- **ADR-0002 (score formula + three-representative contract) and ADR-0006 (no typed
  wrapper for the terminal candidate-row Evidence artifact) are respected and untouched.**

- Lineage: 2026-05-29 architecture review candidate 6 → aegis-rd-uvv (behaviour
  hardening, PR #46) → this (structure/locality). Top recommendation of the 2026-06-09
  review.

## Empirical justification for exclusion-by-key replacing masking

An Invalid cash-holder (all-NaN indicator → all-NaN target weights → `valid_only=True`
means "no rebalance" → cash book) scores `total_return=0.0` (FINITE), `exit_trades.
count()=0`, `sharpe=NaN`. A money-loser scores `total_return=-0.86`. Under a metric
finite-for-cash like `total_return`, the Invalid `0.0` OUTRANKS real losers and would be
selected — masking-to-NaN was the only thing stopping it. Exclusion-by-key makes that
structural: the verdict excludes the key regardless of the finite score it simulates to.
The pollution is metric-dependent: under Sharpe the cash-holder is NaN anyway, so the bug
only bites finite-for-cash metrics. The regression test (tracked as kj5.4) must rank by a
finite-for-cash metric — not Sharpe — else it passes vacuously.

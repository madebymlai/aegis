# Give the Candidate Grid one home behind a value object

Status: accepted

The Candidate Grid — one row per (Candidate, Split), one column per registered Metric —
is the interchange between the optimization sweep, validity classification, ranking, and
held-out attachment, but it travelled as a bare `pd.DataFrame`. Its shape contract was
enforced twice and assumed a third time:

- `ranking.py` validated MultiIndex → `"split"` level → param levels, then derived
  `group_level`;
- `candidate_validity.py` carried a **verbatim duplicate** of that block with its own
  `split_level = "split"` literal;
- `runner.py` built the grid (`_tidy_grid`), re-derived param names by excluding
  `SPLIT_LEVEL` in two places, and re-implemented per-split metric extraction
  (`_candidate_split_metrics`) that `ranking.py` also implements for Selection metrics.

Beyond validation, the candidate-wise iteration idiom (`groupby(level=group_level,
sort=True)` + key-tuple normalization) was duplicated across ranking and validity, and the
split→metric→value extraction (`{split: {metric: optional_float(v)}}`) across ranking and
the runner. The test suite mirrored all of it: `_grid`/`_grid_with_trades` fixture helpers
existed near-verbatim in both the validity and ranking test files.

We give the grid one home: a frozen value object `CandidateGrid` in
`optimization/candidate_grid.py`, constructed at the `_sweep` seam for **both** phases
(the Selection grid and the Held-out grid are two instances of one concept), validated
once in `__post_init__` so every instance — including factory-built test grids — is valid
by construction. Its read surface speaks plain mappings, not pandas: consumers receive
per-candidate `split → metric_id → float | None` mappings with NaN already normalized to
None. The DataFrame is a private spine; pandas dies at the grid boundary.

The interface:

- `CandidateGrid.from_sweep(stacked)` — absorbs `_tidy_grid`: the vbt row-stack guard and
  normalization, then delegates to the validating constructor.
- `by_candidate() -> Iterator[tuple[CandidateKey, SplitMetrics]]` — absorbs the
  groupby + key-tuple idiom. **Parameter-sorted iteration is a documented guarantee**:
  ranking's tie-stability ("ties keep candidate parameter-sorted order") rides on it.
- `split_metrics(key) -> SplitMetrics` — absorbs both copies of the split→metric→value
  extraction (ranking's Selection loop and the runner's `_candidate_split_metrics`).
- `param_levels`, `metric_ids` — replace ad-hoc re-derivation; consumers keep their own
  preconditions (ranking's ranking-metric membership check, validity's `total_trades`
  membership check) but read them off these properties.

`classify_candidates` and `select_representative_candidates` take `CandidateGrid` instead
of `pd.DataFrame`. The `"split"` level name, param-level derivation, `group_level`
construction, key-tuple normalization, and NaN→None conversion become private to the grid
module; `SPLIT_LEVEL` and `optional_float` leave ranking's export surface (the runner
imported them only to feed the absorbed patterns). Construction raises plain
`TypeError`/`ValueError` — no test pinned `OptimizationRunnerError` to the old
`_tidy_grid` guard, and the grid module must not import the runner's error type
(dependency direction). The runner's `NoResultsException` wrap stays in the runner.

## Considered options

- **Free-function module over bare DataFrames** (shared `validate_grid()` + helpers,
  consumers keep `pd.DataFrame` signatures): rejected. Centralizes the knowledge but
  enforces nothing — each consumer must still call validate or trust its caller, so
  "validated exactly once" stays a convention rather than a property of the type.
- **Minimal dedup** (extract only the duplicated validation block): rejected. The
  iteration and extraction duplications — the larger share of the spread knowledge —
  survive untouched.
- **Sub-frames at the boundary** (`by_candidate()` yields `pd.DataFrame` per candidate):
  rejected. Hides the index contract but leaks the frame; ranking's split-label poking and
  the dict extraction survive, and consumer tests still build and inspect frames.
- **Rule-shaped accessors** (`is_all_missing(key, metric)`, `min_scored_value(...)`):
  rejected as an ADR-0010 boundary violation. Each accessor encodes half a verdict rule
  (dropna-then-min *is* the trade-floor's semantics), migrating exclusion knowledge into
  the grid. The grid deepens the *data* the verdict reads, never the rules: non-trading,
  under-traded, and the score formula stay verbatim in validity and ranking.
- **Code-only vocabulary, no glossary term** (the Verdicts precedent from ADR-0010):
  rejected for this concept. "Verdict" was a new word for machinery nothing referenced;
  "the grid" was already load-bearing *inside* CONTEXT.md — the Degenerate Candidate
  definition said "cannot represent the grid" with no definition to resolve to. Minting
  **Candidate Grid** repairs the dangling reference (best/median/worst are exactly the
  grid's three representatives) and disambiguates against the word's older referent, the
  *parameter* grid (cf. the tombstoned `candidate_grid` preflight config key, which
  budgeted the search space — a different thing, now told apart by definition).

## VBT alignment (verified against vbt source)

The two facts the grid freezes are vbt conventions, not laws — which is why they need one
home:

- The `"split"` level name comes from the splitter's split-labels index name. It is vbt's
  *default*, configurable per splitter (custom labels yield e.g. a `split_year` level), so
  it must live in one module, not be hard-coded in three.
- Level order is a vbt merge detail: `row_stack_merge` ends in `pd.concat(keys=split_labels)`
  + `clean_index`, which *prepends* the split level — the real sweep index is
  `(split, *params)`. Consumers survive only by deriving param levels order-agnostically;
  `param_levels` freezes that posture in one place.

vbt offers no competing abstraction: its cross-validation docs consume the merged sweep
result as a bare frame with ad-hoc pandas (`xs`/`unstack`/`groupby`), and `cv_split`'s
per-split `selection` callback is the model ADR-0002 already rejected for global ranking.
`from_sweep` consumes `Splitter.apply` output as-is — no vbt machinery is reimplemented,
and the DataFrame spine stays inside the object so vbt-native analytics can become a grid
method later without consumers re-learning the shape.

Because `Splitter.apply(filter_results=True)` may drop `(split, param)` rows, the grid
does **not** promise rectangular completeness: `by_candidate()` yields the splits actually
swept, which is what both consumers already assume ("the thinnest split it actually
scored") and what the runner's `_nan_metric_frame` "skip compute, keep grid shape" guard
preserves.

## Consequences

- New module `optimization/candidate_grid.py`; deleted from the runner: `_tidy_grid`,
  `_candidate_split_metrics`, both param-name re-derivations; deleted from ranking:
  the validation block, the groupby idiom, the Selection-metrics extraction loop, the
  `SPLIT_LEVEL` and `optional_float` exports; deleted from validity: the duplicated
  validation block and groupby idiom. Validity and ranking go pandas-free.
- **ADR-0006's typed-row rejection is respected, not contradicted.** That rejection
  protected terminal Evidence artifacts (schema-versioned, hash-stable,
  persisted). The Candidate Grid never persists and never appears in Evidence or CLI
  output — it is internal spine, and house precedent (ADR-0003/0005/0006) is "type the
  internal spine, keep terminal artifacts dicts".
- **One deliberate hardening (2026-06-10 implementation review).** The Invalid rule's
  legacy fallback for non-numeric output blocks (classify by element presence via
  ``pd.notna``) is removed, not ported: a non-numeric block is a broken Indicator
  contract and now raises TypeError instead of being classified. Unreachable through the
  production precompute path (indicator outputs are float arrays); fail-loud per house
  robustness rules. This is the one knowing exception to "rules verbatim".
- **ADR-0010's one-owner-two-step verdict is untouched.** `classify_candidates` keeps its
  signature shape (`invalid_keys`, `min_trades`, `metric`) and all three exclusion rules;
  ranking keeps score math and slot selection; `OptimizationResult` is still born exactly
  once in ranking. ADR-0002's score formula and three-representative contract are
  untouched.
- `CandidateKey` stays in `precompute.py`: it is needed at Stage 0 (key materialization)
  before any grid exists, and moving it would point precompute's imports at a later
  pipeline stage for zero depth gain. The grid imports it, as validity does.
- One test factory `make_candidate_grid(spec)` joins
  `tests/support/research/aegis_research/factories.py`, spec in the boundary vocabulary
  (`{candidate: {split: {metric: value}}}`), constructing through `from_sweep` so every
  test grid exercises the production path. The twin `_grid`/`_grid_with_trades` helpers in
  the validity and ranking test files are deleted; shape-contract tests (missing split
  level, no param levels, not a MultiIndex) move out of consumer tests into
  `test_optimization_candidate_grid.py`.
- **Regression oracle: the grid never persists, so no Evidence/Manifest bytes may move.**
  `manifest.json` and the optimization Evidence must stay byte-identical (golden-bytes
  style, per ADR-0003/0004 precedent). *Correction (2026-06-10 implementation review):*
  the originally cited proof did not exist — the two-phase integration test exercises
  behaviour but never persists or compares bytes. The real oracle was built as
  aegis-rd-0vh: `test_optimization_run_golden_bytes.py` executes a full synthetic Run
  through the CLI and compares the persisted Manifest — volatile fields masked,
  re-serialized in Canonical Form — byte-for-byte against a committed golden.
  Optimization Evidence is embedded in the Manifest (there is no separate
  `evidence/optimization.json` file), and the Manifest's artifact content hashes pin
  the other persisted artifacts transitively.
- CONTEXT.md gains **Candidate Grid** and the Degenerate Candidate definition now
  references it (both edits applied with this ADR).
- Lineage: 2026-06-10 architecture review candidate 1 (top recommendation), grilled and
  accepted 2026-06-10.

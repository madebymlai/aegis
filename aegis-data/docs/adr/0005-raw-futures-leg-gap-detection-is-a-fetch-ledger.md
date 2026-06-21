# Raw Futures Leg gap detection is a Fetch Ledger, not Covered-History coverage

Status: accepted

## Context

`RawLegCache` decides which sub-windows of a request it has not yet fetched for a
Raw Futures Leg, so it pulls only gaps. It answered that question by routing
through the frame-in `StoreCoverage.gaps(window, observed)` — which actually
answers a *different* question: "which expected calendar bars are missing from
this frame?" To bridge the mismatch, the cache fabricated sentinel `1.0` "bars"
over each recorded fetched window (`_coverage_marker`) and merged them with the
real observed bars (`_coverage_observed`) so `StoreCoverage` would see the window
as covered.

Two representations of "what I have for this leg" were thereby reconciled by
synthesizing fake data and pushing it through a coverage check built for another
purpose. A **fetched-but-empty** window — a thin contract that legitimately printed
nothing — could only be expressed by this fabrication. ADR-0002 deliberately scoped
`StoreCoverage` to Covered-History admission (a real, non-null bar/rate is present);
Raw Futures Legs are source material, not Covered History (ADR-0003: a leg read is
cold-tolerant with no expected-bar grid). The store already recorded fetched windows
as half-open intervals, so the answer existed in interval form — the fabrication was
a round-trip from intervals to fake frames and back.

## Decision

Recognise that leg gap detection is a **fetch-ledger** question, not a coverage
question, and give it its own representation.

- Add a pure, in-process value object `FetchLedger` (with `FetchedInterval`),
  the interval-arithmetic sibling of `StoreCoverage`: `FetchLedger.of(intervals)`
  coalesces a sorted, non-overlapping union; `FetchLedger.gaps(window)` returns the
  requested window minus that union as `CoverageGap`s. It never reads parquet, holds
  no store root, and knows no calendar — "interval-in", as `StoreCoverage` is
  "frame-in".
- `HistoricalStore` exposes one verb, `leg_fetch_gaps(leg, window)`, which reads the
  recorded fetched-interval record and delegates to `FetchLedger`. The store stays
  the sole parquet owner; the cache sees only this verb and the `CoverageGap`s it
  already consumes.
- `merge_leg` records the fetched window in the Fetch Ledger as part of merging, so
  "merged bars over a window" and "recorded fetch of that window" are one atomic
  command. `record_leg_coverage` and `read_leg_coverage` are removed; the leg surface
  collapses to `merge_leg`, `read_leg`, `leg_fetch_gaps`.
- `RawLegCache` deletes `_coverage_marker` / `_coverage_observed` and no longer
  imports `StoreCoverage`. "Covered" for a leg means "recorded as fetched", not
  "observed bars look complete".
- `StoreCoverage` is **not** modified and legs never route through it.

A `FetchedInterval` denotes a *covered* fetched window, correcting the prior misuse
of `CoverageGap` (an *uncovered* gap) to carry fetched intervals.

## Considered and rejected

- **A coverage-mask channel folded into `StoreCoverage` (Direction B).** Keep routing
  leg gaps through `StoreCoverage`, but represent "fetched-but-empty" as an explicit
  observed-intervals mask instead of fabricated rows. Rejected: it introduces a
  second, contradictory notion of "covered" — covered with *no bar present* — into
  the one module whose identity is "a real non-null bar/rate equals covered". The
  tell is the asymmetry it forces: the mask is admissible on `gaps` but must be
  forbidden on `slice` / `assert_covered`, so the module would hold two coverage
  truths. That is the semantic widening ADR-0002 bought its way out of. Its one
  genuine advantage — reusing calendar-aware, session-grouped gap *granularity* — is
  moot here, because the leg gap drives a provider fetch over a *date range*, which
  wants coarse interval gaps, not session-grouped bars.

- **A `LegLedgerRepository` port with parquet and in-memory adapters.** Rejected on
  seam discipline: ADR-0002 already states that the second-backend seam is the
  store's read functions, and ADR-0003 made `HistoricalStore` the sole owner of leg
  parquet. A repository would split the leg-coverage file-format secret across two
  modules, and its only second adapter would be test-only (the store is already
  test-seamed via a temp root) — a one-implementation abstraction (YAGNI).

- **Keeping the interval arithmetic as a private free function in `store.py`.**
  A defensible, smaller change, but it re-accretes pure gap math into the I/O module
  that ADR-0002 worked to keep thin. Lifting it into `FetchLedger` mirrors the
  established split (pure math module + store-owns-I/O) and makes the interval
  algebra unit-testable with no parquet.

## Consequences

- The `1.0` sentinel fabrication is gone; the "fetched-but-empty" fact lives honestly
  in the Fetch Ledger. A fetched-but-empty window reads as covered with no fabricated
  rows.
- `StoreCoverage` stays pure and frame-in; ADR-0002 holds by construction, and a
  future architecture review has a recorded reason not to re-suggest unifying legs
  into the coverage module.
- The Raw Futures Leg store surface is three verbs; `merge_leg` enforces the
  "merged ⇒ recorded" invariant, so no path produces bars-without-a-ledger-entry.
- The interval algebra is unit-testable parquet-free, mirroring `test_store_coverage`.
- `CONTEXT.md` gains the **Fetch Ledger** term, naming the legs-are-not-Covered-History
  distinction.

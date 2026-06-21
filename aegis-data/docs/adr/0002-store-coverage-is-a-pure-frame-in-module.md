# Store Coverage is a pure, frame-in module; the store owns I/O

Status: accepted (implemented)

## Context

The Historical Store's coverage logic — expected-bar index by trading calendar,
observed-vs-expected reconciliation, gap-run grouping, futures interior-tolerance,
and the per-array / `rate` completeness rule — lived as ~14 private helpers smeared
across `store.py`, each re-threading the same `(arrays, timeframe, calendar, start,
end)` primitives. Coverage is consumed three ways, across **two frame provenances**:
the Pull gap-query and the Store Read load frames from parquet, while the
pre-admission guard (`assert_native_bar_coverage`) validates a provider frame that
is *not yet in the store*.

## Decision

Lift the coverage math behind a deep `StoreCoverage` value object, keyed by a
`HistoryWindow(timeframe, calendar, start, end)` and a `Completeness` strategy.
`StoreCoverage` is **pure**: every method takes the observed frame as an argument
(`gaps`, `assert_covered`, `slice`); it never reads parquet, never holds a
`store_dir`, and never knows where the frame came from. `store.py` stays the sole
owner of parquet paths and format — it loads (or supplies a provider frame), then
hands the frame in. Native bars and FX rates are **one** `StoreCoverage`; their only
difference is the `Completeness` predicate (all required arrays non-null vs `rate`
non-null). `StoreCoverage` raises `StoreCoverageError` and returns `CoverageGap`,
completing that existing family.

## Considered and rejected

- **`StoreCoverage(store_dir)` that reads parquet itself** — gives a tidy
  `gaps(window)` call, but splits the parquet-format secret across two modules and
  forfeits parquet-free testing. The coupling is relocated, not removed.
- **A reader port (`AdmittedHistory`) injected into `StoreCoverage`** — keeps
  `gaps(window)` and stays testable, but it models only the *store-backed* frame
  source. The pre-admission guard validates a *provider* frame that is not in the
  store, so the port cannot serve it without either splitting the interface
  (`gaps(window)` vs `assert_covered(window, frame)`) or inverting admission order
  (persisting unvalidated data, then re-reading to validate). It is also a
  one-implementation abstraction (YAGNI); if a second storage backend ever appears,
  the seam for it is `store.py`'s public read functions, not the coverage module.

The price paid: internal callers thread the frame (`gaps(window, observed)`, not
`gaps(window)`). Accepted because all three callers are internal to aegis-data and
deciding frame provenance is exactly what `store.py`, the I/O adapter, exists to do.

## Consequences

- Coverage bugs land in one module; interior-tolerance, intraday session expansion,
  and gap grouping become unit-testable over synthetic indices with no parquet.
- `store.py` shrinks toward a pure parquet I/O adapter; the scattered
  `if path.exists()` branches collapse into "load-or-empty," and the absent-data
  failure emerges from the coverage math as a `StoreCoverageError`.
- `_missing_fx_rate_index` and the duplicated native/FX skeleton are deleted.
- For future readers: do **not** give `StoreCoverage` a `store_dir` or a storage
  port "for convenience" — the provider-frame admission path is the reason it must
  stay frame-in.

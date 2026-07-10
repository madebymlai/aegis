# The catalog window is one coherent read

Status: accepted

Builds on ADR-0006/0008/0009/0010/0011.

## Context

Every consumer of the catalog port assembled the same window by hand: raw
bars, instrument definitions, verified distributions, and the distribution
coverage report, each pulled through a separate port query. The assembly
knowledge — which queries, in which order, and which ids to filter before
asking — was duplicated in the RD market-data adapter and the Trader backtest
data source, and each caller had invented its own partial answers (RD filtered
FX legs before requesting distributions; Trader filtered `CurrencyPair`
definitions; both triaged missing definitions themselves).

That duplication is exactly the review finding: the window is one coherent
projection of the catalog, but no module owned it.

## Decision

- **One query answers the whole window.** `CatalogBackedDataPort.load_window`
  takes the raw-bar request and returns a frozen `CatalogWindow`: OHLCV per
  requested id, the complete definitions, the verified distributions, and the
  distribution coverage report (defaulted to empty so consumers that never
  read it never mention it).

- **The internal ordering is contract, not style.**
  1. The bar coverage-gate / lazy-fill pass runs FIRST: a fill's Step-1 write
     may seed the very definition the completeness check needs, so judging
     completeness earlier would false-positive on ids the fill itself
     resolves.
  2. Definition completeness is judged BEFORE distribution verification: the
     coverage machinery raises its own coverage-gap error when it cannot
     resolve a definition, which would mislabel an authoring problem as
     environmental. Any requested id without a stored definition fails with
     the port-owned authoring error `MissingCatalogDefinitionsError`, naming
     every missing id at once. The name is deliberately distinct from the
     runtime currency package's missing-definition error so the two can never
     shadow each other at an import site.
  3. ONE distribution-verification pass serves both the returned
     distributions and the coverage report: the coverage service's
     single-pass primitive assesses each id's applicability and bar-frontier
     clamp once (`verify_window`), where the gating and reporting paths
     previously recomputed them independently.

- **The port owns applicability, not the callers.** A cash FX pair joins
  futures contracts and continuous roots as not-applicable for distributions:
  a conversion leg in the window's id set is routine, not an error, so the
  read succeeds with a not-applicable coverage row and no caller filters ids
  before asking.

- **The assembly surface retires.** With the window read in place, the
  per-fact queries it subsumes (`load_raw_bars`, `instruments`,
  `distributions` as consumer-facing assembly steps) are scheduled for
  contraction once both consumers migrate — expand–contract, with one
  deliberate survivor: `distribution_coverage_report` remains the diagnostic
  query for ids that cannot enter a window request (continuous roots carry no
  raw bars but still owe RD their not-applicable Run-evidence rows).

## Non-changes

- **ADR-0008** — the pure-fetch provider seam and single-writer rule are
  untouched; `load_window` composes the same fill.
- **ADR-0009** — continuous series stay owned by `ContinuousContractModel`;
  synthetic roots do not enter a window request.
- **ADR-0010** — distribution verification stays internal to the port; the
  single-pass refactor reshapes the service's internals only.
- **ADR-0011** — the error taxonomy is unchanged: `CatalogCoverageGapError`
  and `GapFillProviderError` remain the two environmental errors, raised
  exactly as before. The new authoring error extends the authoring side only.

## Consequences

- Consumers hold one value with the window's run-constant facts; the fake
  surface for tests is the catalog beneath a real port (the port itself is
  never faked) or a hand-constructed `CatalogWindow`.
- A new catalog-owned window fact lands in one place (`CatalogWindow` and the
  read behind it) instead of once per consumer.
- The request type keeps its `RawBarRequest` name until the contraction
  ticket renames it `CatalogWindowRequest`, once the old callers are gone.

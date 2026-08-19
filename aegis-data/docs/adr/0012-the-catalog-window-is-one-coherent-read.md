# The catalog window is one coherent read

Status: accepted, amended by GH #96/#100/#101 and aegis-rd-bo4

The coherent read remains current. Bar and provider-backed Custom Data warming
now run through Nautilus's DataEngine, absence is an empty answer, and adjusted
closes are persisted as Catalog Custom Data before deterministic Distribution
materialisation.

Builds on ADR-0006/0008/0009/0010/0011.

## Context

Every consumer of the catalog port assembled the same window by hand: raw
bars, instrument definitions, materialised distributions, and the distribution
extent report, each pulled through a separate port query. The assembly
knowledge — which queries, in which order, and which ids to filter before
asking — was duplicated in the RD market-data adapter and the Trader backtest
data source, and each caller had invented its own partial answers (RD filtered
FX legs before requesting distributions; Trader filtered `CurrencyPair`
definitions; both triaged missing definitions themselves).

That duplication is exactly the review finding: the window is one coherent
projection of the catalog, but no module owned it.

## Decision

- **One query answers the whole window.** `CatalogBackedDataPort.load_window`
  takes the raw-bar request and returns a frozen `CatalogWindow`: one native
  `RawBarWindow` per requested id, its OHLCV/quote projections, the complete
  definitions, the materialised distributions, and the distribution extents
  (defaulted to empty so consumers that never read them never mention them).
  Native Bars remain the authoritative records for engine consumers; DataFrames
  are projections for vectorized validation and domain consumers, never an
  intermediate serialization format.

- **The internal ordering is contract, not style.**
  1. The bar warming pass runs FIRST: a fill's Step-1 write
     may seed the very definition the completeness check needs, so judging
     completeness earlier would false-positive on ids the fill itself
     resolves.
  2. Definition completeness is judged BEFORE distribution materialisation. Any
     requested id without a stored definition fails with
     the port-owned authoring error `MissingCatalogDefinitionsError`, naming
     every missing id at once. The name is deliberately distinct from the
     runtime currency package's missing-definition error so the two can never
     shadow each other at an import site.
  3. ONE distribution-materialisation pass serves both the returned
     distributions and the extent report: the materialiser's single-pass
     primitive assesses each id's applicability and bar-end clamp once, where
     the materialisation and reporting paths
     previously recomputed them independently.

- **The port owns applicability, not the callers.** A cash FX pair joins
  futures contracts and continuous roots as not-applicable for distributions:
  a conversion leg in the window's id set is routine, not an error, so the
  read succeeds with a not-applicable extent row and no caller filters ids
  before asking.

- **The assembly surface retires.** With the window read in place, the
  per-fact queries it subsumes (`load_raw_bars`, `instruments`,
  `distributions` as consumer-facing assembly steps) are scheduled for
  contraction once both consumers migrate — expand–contract, with one
  deliberate survivor: `distribution_extent_report` remains the diagnostic
  query for ids that cannot enter a window request (continuous roots carry no
  raw bars but still owe RD their not-applicable Run-evidence rows).

## Non-changes

- **ADR-0008** — instrument-definition seeding remains separate. Bar and
  provider-backed Custom Data gaps and write-back are now owned by Nautilus's
  DataEngine (GH #101, aegis-rd-bo4).
- **ADR-0009** — continuous series stay owned by `ContinuousContractModel`;
  synthetic roots do not enter a window request.
- **ADR-0010** — Distribution materialisation stays internal to the port, now
  deriving from stored traded and adjusted-close inputs without markers.
- **ADR-0011** — provider faults still cross the port as
  `GapFillProviderError`; Catalog absence is no longer an environmental error.

## Consequences

- Consumers hold one value with the window's run-constant facts; the fake
  surface for tests is the catalog beneath a real port (the port itself is
  never faked) or a hand-constructed `CatalogWindow`.
- Every distribution-bearing instrument carries its raw **daily** series in
  the catalog regardless of the timeframe it trades: the dividend decode
  compares daily trade closes against the vendor's daily `ADJUSTED_LAST`, so
  an hourly-traded instrument's `1D` bars are read by materialisation on every
  window load. A provider-backed load gap-fills them automatically; an
  offline absence reads empty and is governed operationally by Warm Then Sweep.
- A new catalog-owned window fact lands in one place (`CatalogWindow` and the
  read behind it) instead of once per consumer.
- Trader feeds the window's native Bars directly to Nautilus's backtest engine.
  It does not regenerate Bars from the OHLCV projections, so catalog price,
  volume, type, and nanosecond timestamps remain intact end to end.
- The request type keeps its `RawBarRequest` name until the contraction
  ticket renames it `CatalogWindowRequest`, once the old callers are gone.

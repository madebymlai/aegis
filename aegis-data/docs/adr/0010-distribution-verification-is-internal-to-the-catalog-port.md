# Distribution verification is internal to the Catalog port; the port owns the clock

Status: superseded in part by GH #96/#98/#100

Distribution materialisation remains internal to the Catalog port. Its marker
ledger and injected marker clock were retired; stored traded and adjusted-close
inputs now make the materialisation deterministic, while absence reads empty.
The calculation is exposed as a local Custom Data provider: native
`RequestData(update_catalog=True)` owns gap discovery and Catalog write-back, so
the former Aegis-owned `Catalog.fill` algorithm no longer exists.

Reinforces ADR-0008.

## Context

ADR-0008 declared one enforcement seam for distributions: research and Trader
obtain them through `CatalogBackedDataPort.distributions(...)`, a verified read
that proves the bounded window was checked against an adjusted-last source.
Production honoured this — but the verification tests and the RD seeded-catalog
fixture bypassed the seam, constructing `DistributionCoverageService` directly
from a second public module.

Every bypass existed for exactly one reason: the port built the coverage
service internally with the ambient wall clock, so any caller needing a
deterministic `checked_at` marker stamp (the coding standards require injected
clocks in tests) had to go around the port. The result was two public modules
whose interfaces nearly mirrored each other (`ensure_covered` /
`coverage_report` / `force_reverify` vs. the port's `distributions` /
`distribution_coverage_report` / `force_reverify_distribution_coverage`), and
an implementation that could not change without breaking importers outside the
package.

## Decision

- **The Catalog port accepts the clock.** `CatalogBackedDataPort` carries
  `clock_ns: Callable[[], int]` (defaulted to the wall clock) and threads it
  into every coverage-service construction. The port stamps `checked_at` into
  durable catalog data, so time is a real dependency of the port. The coding
  standards resolve the interface-width objection themselves: they name
  injected clocks as the sanctioned remedy for uncontrolled variation, which
  classifies the field as a dependency made explicit — not a hook added only to
  make tests easier. It is composition of the same species as the port's
  former distribution-provider dependency and `definition_seeder` field; the method
  surface does not grow.

- **The verified read is the ensure.** Arrangement that needs a verified
  window calls `distributions(...)` — per ADR-0008 the read *is* the
  verification — and may assert its result (the RD zero-distribution fixture
  asserts the read returns no events, so a synthetic Catalog that grows
  distributions fails loud at arrangement time). No ensure-only or
  force-reverify command is kept: re-verification is expressed by clearing
  coverage and performing the verified read again. The former
  `force_reverify_distribution_coverage` command had no production callers and
  duplicated the verified-read seam.

- **The coverage module is internal.** `_distribution_coverage.py` keeps the
  file decomposition but stops being public API; `DistributionCoverageService`
  and `DistributionCoverageMarker` are the port's secret. Its only importer is
  `catalog.py` (lazily, inside the port methods).

- **The provider Protocol lives beside the port.** The former distribution-provider
  Protocol was interface vocabulary — the type of the port's corresponding
  field — so it moved into `catalog.py` next to the Bar provider port; the
  internal module imports it from there.

- **Test controls cross the production seam.** Tests and fixtures build a
  `CatalogBackedDataPort` with a pinned `clock_ns` and drive verification
  through the same methods production calls. The interface is the test surface.

## Considered and rejected

- **An arrangement helper on `aegis_data.testing`** (pin coverage via a blessed
  test-support function; port interface untouched). Rejected: the force-reverify
  tests would then run the port command against the wall clock — uncontrolled
  variation the reliability standard says to remove by injecting clocks — and
  one literal assertion would degrade to a relational one. It also grows a
  second, test-only surface that mirrors the service it is meant to hide.
- **Relational assertions instead of pinned time.** Rejected: breaks the
  literal-expected-values test standard, and an unpinned RD fixture leaks
  nondeterminism into anything that later snapshots provider metadata.
- **Monkeypatching the module clock.** Rejected: ambient authority — behaviour
  altered from outside any interface.
- **Public-but-documented coverage module.** Rejected as unenforceable; the
  bypasses this ADR removes are the counterexample.

## Consequences

- The coverage implementation (marker ledger, applicability polarity, frontier
  clamping) can change without touching anything outside `aegis_data`.
- The unused force-reverify operator command is removed; clearing coverage and
  calling the verified read is the one re-verification workflow.
- Deterministic `checked_at` is available to any caller through the port, so
  there is no remaining reason to construct the service directly.
- The marker's parquet layout and serialization key off the class name, not the
  module path, so the rename is invisible to markers already stored in real
  Catalogs; the warm-read tests exercise this.

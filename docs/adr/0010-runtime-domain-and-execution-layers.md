# `aegis-runtime` has domain and execution layers

Status: accepted (implemented). **Supersedes ADR-0006** by generalising its
one-value decision into the package rule that owns every shared runtime value.

## Decision

`aegis-runtime` remains one distribution and one published top-level facade,
but its implementation has two enforced layers:

- `aegis_runtime.domain` owns dependency-free, in-memory values and policies
  shared across the research and trader dependency arrows: the Array value
  object, Component Strategy inputs, drift bands, exposure limits and
  validation, currency conversion and units, financing, futures-root
  validation, and re-basing algebra.
- `aegis_runtime.execution` owns the Execution Bundle, `DataContract` and wire
  vocabulary, payload loader, and roll-sensitivity orchestration. Execution may
  import domain; domain may never import execution.

A value shared across the dependency arrow is domain-layer-owned because the
graph forces that home. `MarketDataBundle`, the re-basing algebra, and
`ComponentStrategyInputs` are instances of this one rule, not isolated moves.

Pydantic marks the serialization boundary. Types serialized into an Execution
Bundle payload are configured in the execution layer; in-memory domain values
remain plain frozen dataclasses. An Import Linter forbidden contract prevents
the domain layer from importing pydantic, and a layers contract prevents upward
domain-to-execution imports. Both contracts run in CI.

## Considered and rejected

- **A separate domain distribution**: rejected. Domain and execution neither
  version nor deploy independently, and no current consumer wants domain
  without execution. The only useful boundary is import direction, which the
  linter enforces without a second release surface.
- **Let execution depend on `aegis-data`**: rejected. Although the data
  package's runtime dependency was unused and is removed, reversing the arrow
  would pull catalog and ingestion dependencies into the minimal live
  Execution Bundle path.
- **Pydantic domain values**: rejected. It cannot meaningfully validate the
  DataFrames and rate series involved, adds construction work to the `1 + R`
  decision path, and would put serialization machinery onto a byte-pinned
  in-memory seam.
- **Compatibility modules at the previous submodule paths**: rejected by the
  Forward-First principle. First-party direct imports move to the new owner;
  the unchanged top-level facade remains the published contract.

## Consequences

- Every implementation module belongs to exactly one of the two layers.
- The public `aegis_runtime` export list is unchanged, so callers using the
  published facade and generated Execution Bundles need no re-export or version
  floor change.
- `MarketDataBundle` can be imported directly by both currency conversion and
  the roll probe, removing the need for reflective reconstruction.
- `aegis-data` no longer declares or type-suppresses an unused
  `aegis-runtime` dependency.

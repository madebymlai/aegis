# RunData is the single research data interface

Status: accepted

Supersedes ADR-0020, ADR-0024, ADR-0025, and ADR-0027. Amends ADR-0015 and
ADR-0026. Origin: epic `aegis-rd-0iom`, accepted 2026-07-22.

## Context

The research data path accumulated several values that described different
stages of the same load: `MarketDataResult`, typed metadata and quality facets,
`RunArrays`, and `RunDataFacts`. Callers coordinated those values, reconstructed
their projections, and depended on the structure of the loader. A separate
`aegis_research.data` facade and `market_data` package advertised this machinery
as a public interface even though the Nautilus catalog port is the only source.

## Decision

`load_run_data(config, required_arrays, port, custom_data_providers)` is the one
deep research data operation. It returns one frozen `RunData` value containing:

- the kernel-owned `MarketDataBundle` used by Components;
- the shared `InstrumentResolution` for tradeable identity and drift bands;
- currency conversion, distributions, and catalog size increments needed by
  portfolio simulation;
- adjustment-mode and structural load Evidence used by manifests, Candidate
  identity, and artifacts.

The operation owns catalog reads, continuous-future materialisation, custom
Arrays, base-currency conversion, validation, and Evidence construction. It
fails environmental load problems as `RunDataUnavailable`, carrying Evidence
that the orchestrator persists before marking the Run failed. Authoring and
contract errors remain loud validation failures.

`DataArrayContract` continues to exist before loading so a Run can record and
validate its declared Array requirements. Its projections combine with
`RunData` through pure functions in `optimization/run_data_contract.py`; it is
not a second loader result. The Metric Registry fingerprint remains optimization
provenance and is passed separately.

`InstrumentResolution` is the only tradeable identity value. It owns the native
and continuous ordering and projects portfolio drift bands. Both portfolio
simulation and Execution Bundle export consume that same resolution. Marking
declarations belong to `DataConfig`, which builds the resolver used by the
catalog port.

The legacy `aegis_research.data` facade, the entire `market_data` package, and
the shallow `drift_bands` module are deleted without aliases. Configurable data
quality/degradation policy and success-state fields such as skipped or
unavailable Arrays are deleted. A successful `RunData` is valid by
construction; a failed load is not represented as a partially usable success
value. No old-schema reader or compatibility projection is provided.

## Consequences

- A caller performs one load and passes one coherent value through the Run.
- Source format, continuous construction, conversion, and Evidence schema have
  one owner and can change without widening pipeline interfaces.
- Components still receive the stable kernel `MarketDataBundle` Array interface;
  research does not define or re-export another copy.
- Historical artifacts and ADR text remain historical. Current code and docs
  refer to `RunData`; previous Candidate identities are intentionally not
  translated forward.

**Amendment (2026-07-23).** The Manifest is the only durable RunData audit projection.
`data_metadata.json`, its artifact record, and its planning/write/failure choreography are deleted
because they duplicated `evidence.data` and had no production reader. Successful and unavailable
loads retain their existing RunData Evidence; loading, instrument resolution, adjustments, and
Array validation are unchanged.

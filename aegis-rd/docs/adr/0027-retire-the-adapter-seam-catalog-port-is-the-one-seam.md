# Retire the adapter seam: the catalog port is the one seam, evidence speaks market_data.v4

Status: superseded by [ADR-0028](0028-run-data-is-the-single-research-data-interface.md)

Amends ADR-0005 (the seam-stays premise). Builds on Data ADR-0011. Origin:
architecture review 2026-07-10, candidate 02; decisions settled by grilling
the same day (epic aegis-rd-1gef).

## Context

ADR-0005 kept the generic `MarketDataAdapter` seam because synthetic, CSV and
remote sources were real. That premise expired: every production source except
the Nautilus catalog was retired, leaving a one-method `Protocol`, a
source-loader registry with zero callers, and an `adapter=` parameter used
only by tests. The seam's remote-era failure machinery (`RemoteDataPullError`,
`provider_failed_adapter_result`, the `provider_failed` state) was unreachable
from production — only test fakes could trigger it — while real environmental
failures (coverage gaps, broken fetches) escaped as raw vendor stack traces
and never became Evidence. The `market_data.v3` artifact and the Run Config
still carried remote/VBT-loader vocabulary and knobs.

## Decision

- **The seam is deleted, not renamed.** The adapter `Protocol`, the registry,
  and `adapter=` are gone. The catalog loader is *the* implementation behind
  `load_market_data_result`, which carries a `port=` passthrough
  (`CatalogBackedDataPort`) as the one injection seam — identical to
  production wiring, so tests and callers cross the same seam. One adapter
  means a hypothetical seam; the real seam is the port (Data ADR-0008).

- **The failure contract is the unavailability family, reimplemented.**
  `MarketDataUnavailableError` · quality state `data_unavailable` · internal
  handoff `MarketDataLoad` with `failed_market_data_load`. The catalog loader
  — the only module that talks to the port — owns environmental-vs-authoring
  triage: it wraps the port's two environmental errors
  (`CatalogCoverageGapError`, `GapFillProviderError`, Data ADR-0011) into the
  RD error; authoring errors keep crashing. The orchestrator catches exactly
  the RD error and collapses it through the unchanged observe → judge →
  describe sequence (ADR-0005's decomposition survives intact). The gate's
  judgement rides the failed load's index evidence (`unavailable_reason`), so
  the judge stays pure and the verdict quotes which intervals cannot be
  served.

- **The facade is the deep interface.** `data.py` exports the load entry
  points, `MarketDataResult` and its typed parts, the quality-state
  vocabulary, and `MarketDataUnavailableError`. The loader and the handoff
  are implementation.

- **Evidence reshapes once to `market_data.v4`.** The six-facet shape
  survives; inside it: provenance shrinks 12 → 6 (`provider_class` →
  `source_class`, `provider_metadata` → `port_metadata`;
  `omitted_metadata_fields` dropped — verified: nothing ever set it;
  `update_supported` and `missing_index` kept; the five loader knobs
  dropped). Failure values renamed: source-metadata keys `error_type` /
  `error_summary`; the index-evidence marker `data_unavailable`;
  per-instrument `provider_status` → `load_status`
  (`loaded` / `data_unavailable` / `skipped`).

- **The Run Config authoring break is loud.** `missing_columns`,
  `tz_localize`, `tz_convert`, `skip_on_error`, `silence_warnings` left
  `DataConfig`; strict validation (`extra="forbid"`) names the offending
  field. `missing_index` stays — it drives the loader's calendar-intersection
  drop policy. The retired knobs' values are pinned inside the loader's VBT
  projection (`missing_columns="raise"`, no tz coercion). Verified before
  deleting `skip_on_error`: the production loader cannot emit the `skipped`
  status (panels always carry every tradeable id), and the old validator made
  the knob redundant with the `skipped_instrument_ids` degradation — the
  quality policy is now the single control for the leaf-reachable skip
  scenario.

- **Goldens re-pinned once as a recorded reset** (the ADR-0020 precedent):
  the optimization-run manifest golden and the resolved-config oracle hashes
  moved together with the schema bump.

- **Tests split by altitude.** Loader-reachable scenarios drive
  load → observe → judge → describe through `load_market_data_result(port=…)`
  over seeded corpora; loader-unreachable shapes exercise the ADR-0005 leaf
  interfaces via `result_from_load` with hand-built `MarketDataLoad` values.

## Consequences

- The module carries no knowledge of sources that do not exist; new code
  cannot wire to retired seams by following exports.
- A Run whose window cannot be served ends as judged, reproducible
  `data_unavailable` Evidence (GH #75 closed at the aegis-data end).
- Historical `market_data.v3` artifacts keep their bytes; no reader shim is
  built (forward-first). Old Runs stay verifiable against their own schema.
- **Failure evidence now quotes the port error verbatim** (`error_summary`,
  quality reasons) — deliberately inverting the remote-era rule that provider
  error text never entered metadata. That rule guarded remote credentials in
  `fetch_kwargs`; the catalog path carries none, and the gate's exact missing
  intervals are the verdict a researcher needs in the artifact.
- Net seams across both repos went down by two (the adapter Protocol and the
  registry); the port is both production wiring and the test seam.

## Alternatives considered

- **Keep the Protocol as a private hook** for test injection: rejected — a
  hypothetical seam that only tests cross teaches the wrong architecture; the
  port passthrough gives tests the production seam.
- **Rename the old machinery in place** (`provider_failed` →
  `data_unavailable` etc.): rejected — the remote-era machinery encoded a
  mechanism ("a provider failed"), not the domain fact ("the window cannot be
  served"); it was deleted and the unavailability family built new.
- **v4 as a minimal rename** (keep the knobs and `omitted_metadata_fields`):
  rejected — vestigial fields in a schema-versioned artifact are permanent
  false facts; one recorded reset is cheaper than carrying them forever.

---
date: 2026-05-16
topic: vectorbt-market-data-contract
---

# VectorBT Market Data Contract

## Summary

Make market data a VectorBT-native, provider-extensible contract. Existing sources should produce a canonical `vbt.Data`-backed market-data result, with Pandas views available only as intentional derived outputs for modeling, portable artifacts, and integrations that need them.

---

## Problem Frame

Market data is the source-of-truth input for every downstream indicator, label, split, portfolio, metric, and report. If the data boundary is weak, downstream results can look reproducible while silently depending on provider defaults, shape drift, missing-data behavior, timezone assumptions, or lossy conversion from native provider state.

The current scaffold has started moving in the right direction: `research/aegis_research/data.py` exposes `MarketDataResult`, preserves `native_object` for remote VectorBT providers, and records some metadata. But the effective payload is still DataFrame-first: `load_market_data` returns a plain `pd.DataFrame`, remote `vbt.Data` objects are immediately flattened through `.get()`, synthetic and CSV sources are not wrapped into a native data object, and OHLCV extraction still depends on manual column probing.

VectorBT PRO documentation points to a cleaner contract: `Data` is built to own fetching, wrapping, alignment, timezone handling, missing-index and missing-column policy, updating, caching, resampling, feature/symbol semantics, and Pandas view extraction. This project has no compatibility burden that justifies preserving the weaker DataFrame-first boundary.

---

## Actors

- A1. Experiment author: Chooses a market data source, symbols, timeframe, provider options, and quality policies in experiment config.
- A2. Experiment runner: Loads data and needs failures, skipped symbols, degraded coverage, and provider state to be explicit before downstream work begins.
- A3. Downstream research stages: Consume close/high/low/volume or sklearn-ready arrays without knowing which provider supplied the data.
- A4. Run reviewer or automation agent: Inspects artifacts and metadata to understand data provenance, quality, shape, and reproducibility.
- A5. Future provider maintainer: Adds a new VectorBT provider or custom data source without rewriting downstream indicators, labels, splits, or portfolios.

---

## Key Flows

- F1. Load current supported provider data
  - **Trigger:** A validated experiment config selects `synthetic`, `csv`, `yfinance`, `binance`, or `ccxt`.
  - **Actors:** A1, A2, A3, A4
  - **Steps:** Select the provider, load or pull the data through the provider contract, preserve or create the native `vbt.Data` object, derive stable Pandas views only when requested by downstream stages, and record metadata plus quality status.
  - **Outcome:** Downstream stages receive stable data views while the run preserves native VectorBT data semantics and provenance.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R13, R14, R15
- F2. Add a future VectorBT provider
  - **Trigger:** The project wants to support another VectorBT `Data` subclass, such as Databento/BentoData, after the core contract is in place.
  - **Actors:** A1, A2, A5
  - **Steps:** Map the provider into the same market-data result contract, pass provider-specific public options through a safe boundary, preserve native metadata, and expose the same derived OHLCV/Pandas views.
  - **Outcome:** Provider expansion does not force downstream research-stage rewrites.
  - **Covered by:** R1, R4, R6, R10, R11, R12, R16
- F3. Handle partial, missing, or misaligned data
  - **Trigger:** Provider data has skipped symbols, empty fetches, missing rows, mismatched calendars, duplicate indexes, timezone mismatches, or missing OHLCV features.
  - **Actors:** A2, A3, A4
  - **Steps:** Apply explicit missing-data and alignment policy, classify the data quality state, fail fast when the run cannot satisfy the contract, and record degraded-but-allowed cases when explicitly configured.
  - **Outcome:** Runs do not silently continue with incomplete or shape-drifted data.
  - **Covered by:** R7, R8, R9, R13, R14, R15

---

## Requirements

**Canonical Data Contract**
- R1. The canonical market-data result must be VectorBT-native: it must expose a `vbt.Data` object or provider subclass as the source-of-truth loaded data object.
- R2. The old DataFrame-first contract must not be preserved as the primary API; any Pandas output must be a derived view with documented semantics.
- R3. Supported local sources must participate in the same native contract as remote sources; synthetic and CSV data must be wrapped into a `vbt.Data`-compatible object when practical.
- R4. The market-data result must provide stable derived views for downstream stages that need Pandas or sklearn-ready arrays, without making downstream stages inspect provider-specific objects.
- R5. Single-symbol and multi-symbol runs must have stable feature/symbol semantics; the contract must avoid implicit shape drift caused by squeezing or ambiguous feature/symbol orientation.

**Provider Extensibility**
- R6. Provider selection must support the current source set (`synthetic`, `csv`, `yfinance`, `binance`, `ccxt`) while defining a clear extension path for future VectorBT `Data` subclasses.
- R7. Provider-specific public options must be accepted only through an explicit, safe passthrough boundary rather than new ad hoc top-level fields for every provider.
- R8. Provider-native symbols must be treated as explicit user input unless the contract later defines a visible normalization or mapping rule; silent symbol rewriting is out of scope.
- R9. Provider credentials, sessions, clients, and live settings must stay outside committed public configs and public artifacts; secret references and redaction rules from the config contract continue to apply.
- R10. Adding a future provider must not require downstream indicator, label, split, portfolio, or reporting code to branch on provider identity.

**OHLCV Access And Shape**
- R11. OHLCV extraction must use VectorBT-native `Data` properties or OHLCV accessors where practical, rather than manual probing of flat and MultiIndex column layouts.
- R12. Non-standard OHLCV column names must be handled through an explicit feature mapping concept, not ad hoc column-name detection.
- R13. The data contract must define how close, high, low, open, and volume are exposed to downstream stages, including behavior when a requested feature is unavailable.

**Quality, Missing Data, And Alignment**
- R14. Missing-index, missing-column, timezone-localization, timezone-conversion, cache, refresh, and error-handling policies must be explicit in config or documented defaults before provider data is pulled or wrapped.
- R15. Data quality metadata must include coverage, missingness, duplicate-index handling, timezone, inferred or returned frequency, first and last timestamp, feature availability, per-symbol status, and provider status when available.
- R16. Partial provider failures, skipped symbols, empty fetches, and degraded coverage must never be silently swallowed; they must either fail the run or be recorded as an explicit degraded-but-allowed quality state.
- R17. When a provider supports update/refetch workflows, the contract must preserve enough native state to make missing-data repair possible later; when update is unsupported, that limitation must be visible in metadata or documentation.

**Metadata And Artifacts**
- R18. Market-data metadata must preserve provider class, source, symbols, features, timeframe, fetch kwargs, returned kwargs, timezone policy, missing-index policy, missing-column policy, last-index evidence, delisted status when available, and wrapper/frequency evidence when available.
- R19. Native VectorBT data state that materially affects reproducibility must be eligible for private native persistence, paired with public metadata that automation can inspect without loading the native object.
- R20. Public metadata and artifacts must not expose provider credentials, secret-bearing kwargs, private clients, local usernames, or non-portable absolute paths.

**Fixtures And Coverage**
- R21. Tests must cover synthetic, CSV, and mocked/provider-shaped remote data through the native contract, including single-symbol and multi-symbol cases.
- R22. Tests must cover stable OHLCV access for flat columns, symbol/feature structures, custom feature mappings, missing features, and non-numeric invalid data.
- R23. Tests must cover explicit handling of missing rows, duplicate indexes, timezone normalization, skipped symbols, provider errors, secret-bearing provider options, and future-provider adapter behavior.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given a synthetic or CSV experiment, when market data is loaded, the canonical result exposes a native `vbt.Data`-compatible object and any DataFrame is clearly a derived view.
- AE2. **Covers R4, R5, R10.** Given one-symbol and multi-symbol runs from different providers, when downstream stages request close/high/low data, they receive stable views without branching on provider identity or silently changing shape.
- AE3. **Covers R6, R7, R8, R9.** Given a remote provider config with provider-specific public options and secret references, when data is pulled, public options reach the provider through the safe boundary while credentials remain outside public artifacts.
- AE4. **Covers R11, R12, R13, R22.** Given OHLCV data with standard or explicitly mapped feature names, when close/high/low/open/volume are requested, extraction uses VectorBT-native semantics and fails visibly when required features are unavailable.
- AE5. **Covers R14, R15, R16, R17.** Given a provider returns partial data or a symbol fails, when the run evaluates data quality, the run either fails fast or records a degraded-but-allowed state with skipped symbols, coverage, and repair/update evidence.
- AE6. **Covers R18, R19, R20.** Given a successful remote-provider run, when artifacts are inspected, the reviewer can identify provider class, fetch settings, returned metadata, shape, quality state, and native-data sidecar metadata without exposing secrets.
- AE7. **Covers R6, R10, R21, R23.** Given a future VectorBT provider such as BentoData is added later, when it satisfies the market-data result contract, downstream research stages continue to operate through the same derived views and metadata expectations.

---

## Success Criteria

- Experiment authors can choose current supported providers through one coherent market-data contract instead of learning provider-specific downstream behavior.
- Downstream research stages no longer depend on whether data came from synthetic, CSV, YFData, BinanceData, CCXTData, or a future VectorBT provider.
- Run reviewers and automation can understand data provenance, quality, feature availability, missingness, timezone/frequency assumptions, and provider status from metadata and artifacts.
- The project can add a future provider such as Databento/BentoData as a provider-adapter addition, not a rewrite of indicators, labels, splits, portfolios, and reports.
- A planner can translate this into implementation work without inventing the data contract, provider-extensibility boundary, scope exclusions, or quality expectations.

---

## Scope Boundaries

- No backward compatibility requirement for the old DataFrame-first `load_market_data` contract; the scaffold is allowed to break forward to the cleaner native boundary.
- No explicit Databento/BentoData provider implementation in this issue; Databento is prior-art evidence for extensibility, caching, paid-provider behavior, and raw-trade schemas.
- No raw-trade-to-bar construction contract in this issue; OHLCV sources and explicitly provided OHLCV data remain the baseline.
- No requirement to migrate every downstream stage to `Data.run` or VectorBT-native execution now; Pandas views remain valid at the modeling and artifact boundaries.
- No attempt to make every VectorBT provider option a first-class config field; provider-specific public options belong behind an explicit passthrough boundary.
- No committed credentials, private provider clients, or provider sessions in public config or public artifacts.
- No hosted experiment-tracking product or broad data lake/cache system; this remains the local research scaffold data contract.

---

## Key Decisions

- Native core, derived views: `vbt.Data` becomes the authoritative data-stage object, while Pandas remains an intentional boundary for tools that need it.
- Break the weak contract: Preserving the old DataFrame-first API would keep the metadata-loss problem alive.
- Provider-extensible, not provider-expansive: The contract should make future providers easy to add, but issue 6 should harden existing providers first.
- Current-source parity: Synthetic and CSV data must not be second-class relative to remote providers; they should produce comparable native state and metadata.
- Explicit degraded states: Partial data is acceptable only when the run records it visibly and the config/policy allows it.
- VectorBT conventions first: Use `Data`, `Data.from_data`, provider subclasses, OHLCV accessors, feature maps, update state, and cache controls where they fit instead of duplicating those semantics in local helpers.

---

## Dependencies / Assumptions

- The config-contract requirements in `docs/brainstorms/2026-05-16-experiment-config-contract-requirements.md` define the safe config, secret-reference, passthrough, and redaction boundary this work should reuse.
- The provenance-contract requirements in `docs/brainstorms/2026-05-16-experiment-provenance-contract-requirements.md` define the broader run-manifest and native-artifact expectations this data contract should feed.
- Current data loading lives in `research/aegis_research/data.py`, and current orchestration consumes it from `research/aegis_research/experiments.py`.
- VectorBT PRO MCP documentation confirms `Data` is intended to own fetching, wrapping, alignment, updating, caching, resampling, feature/symbol semantics, and Pandas view extraction.
- The Brett Goulder Databento gist is relevant prior art for provider extensibility and caching concerns, but it is not the target implementation shape because it returns DataFrames, manually caches parquet files, and prints/continues through errors.
- The project principles in `AGENTS.md` favor forward-first contracts, fail-fast behavior, explicit error types, and no silent error swallowing.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R3, R4][Technical] What exact market-data result API should expose the native object, derived views, OHLCV accessors, metadata, and quality state?
- [Affects R6, R7, R10][Technical] What provider-extension mechanism best supports current sources and future VectorBT `Data` subclasses without allowing unsafe arbitrary imports or secret leakage?
- [Affects R5, R11, R12, R13][Needs research] What exact VectorBT calls and options should be used to keep feature/symbol orientation stable across single-symbol, multi-symbol, flat-column, and custom-mapped OHLCV inputs?
- [Affects R14, R15, R16][Technical] What default missing-data, alignment, and degraded-state policies should schema version 1 use for baseline research runs?
- [Affects R17, R18, R19][Needs research] Which provider metadata fields are stable and useful enough to persist for YFData, BinanceData, CCXTData, and locally wrapped Data objects?
- [Affects R21, R22, R23][Technical] What mocked provider fixtures best simulate native VectorBT provider objects without making tests depend on live remote services?

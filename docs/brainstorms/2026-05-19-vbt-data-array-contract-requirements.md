---
date: 2026-05-19
topic: vbt-data-array-contract
---

# VBT Data Array Contract

## Summary

Make run data inputs explicit, VBT-first, and component-driven: configs list the VBT data arrays a run expects, components declare the VBT arrays they require, and the runner validates that the loaded data satisfies both before execution.

---

## Problem Frame

The current data boundary is moving toward a bundle that exposes common OHLCV panels, but a fixed bundle shape is not extensible enough for real research workflows. Indicators and strategies may need VBT-native arrays beyond the five standard OHLCV fields, and adding those by hardcoding new bundle attributes would recreate the same coupling each time a provider or dataset grows.

At the same time, letting run configs become arbitrary column-mapping or parameter-passing surfaces would weaken the experiment contract. The project wants VBT-first data semantics: configs should name the arrays expected from the data source using VBT feature names, while providers and local data ingestion are responsible for exposing those arrays in a VBT-compatible shape.

---

## Actors

- A1. Experiment author: Declares which data arrays a run expects and selects components by stable id.
- A2. Component author: Declares required input arrays in component metadata and writes component code against those arrays.
- A3. Experiment runner: Loads market data, expands array shortcuts, validates component requirements, and fails before execution when arrays are unavailable.
- A4. Run reviewer or automation agent: Reviews artifacts and config to understand exactly which raw data arrays the run depended on.
- A5. Provider or data-source maintainer: Ensures each supported source exposes requested arrays through VBT feature semantics.

---

## Key Flows

- F1. Configure a run's data arrays
  - **Trigger:** An experiment author writes or reviews a run config.
  - **Actors:** A1, A4
  - **Steps:** The author selects the data source, symbols, and explicit VBT data arrays needed by the run; common OHLCV needs may use the OHLCV keyword; extra arrays are listed by exact VBT feature name.
  - **Outcome:** The run config visibly states its data dependency before any component executes.
  - **Covered by:** R1, R2, R3, R4, R5
- F2. Validate selected components against data arrays
  - **Trigger:** The runner resolves selected indicator, label, or strategy components.
  - **Actors:** A2, A3, A4
  - **Steps:** The runner expands configured array shortcuts, reads selected component input declarations, compares the required arrays with the configured array set, and rejects mismatches before running component code.
  - **Outcome:** Component input requirements cannot silently pull additional arrays that were not declared by the run.
  - **Covered by:** R4, R6, R7, R8, R9
- F3. Load provider data for requested arrays
  - **Trigger:** A validated run begins data loading.
  - **Actors:** A3, A5
  - **Steps:** The selected data source exposes the requested VBT arrays, the runner verifies availability and shape, and downstream components receive a dynamic data bundle keyed by the requested arrays.
  - **Outcome:** Components consume VBT-shaped arrays without branching on provider identity or relying on run-config column aliases.
  - **Covered by:** R10, R11, R12, R13, R14

---

## Requirements

**Run Data Declaration**
- R1. Run configs must declare the data arrays expected by the run using VBT feature names.
- R2. The standard OHLCV shortcut must expand to the five VBT arrays Open, High, Low, Close, and Volume.
- R3. The OHLCV shortcut must be usable alongside additional exact VBT feature names in the same array list.
- R4. The effective configured array set must be deterministic, deduplicated, and visible to reviewers and automation.
- R5. Close must not be treated as an implicit universal default when a run config is required to declare arrays; the run's data dependencies should be explicit.

**Component Input Contract**
- R6. Component manifests must declare required input arrays using the same VBT feature names as run configs.
- R7. The runner must validate that every selected component's required input arrays are present in the run's effective configured array set before component execution.
- R8. If a selected component requires an array that is not configured, the run must fail as a config/data-contract error before provider data is consumed by that component.
- R9. Component code must read data arrays from the runner-provided data object rather than receiving a fixed close-only input or run-config params.

**VBT-First Data Loading**
- R10. Data sources must expose requested arrays through VBT feature semantics rather than through project-defined alias names.
- R11. The run config must not provide a generic feature or column mapping surface; non-standard local data must be normalized before the run or handled inside a provider/source adapter.
- R12. Loaded data must be validated for every configured array that is required by the run or by selected components.
- R13. The data object passed to components must support dynamic array access by VBT feature name, while convenience accessors for common arrays may remain.
- R14. Missing, empty, mis-shaped, or non-numeric required arrays must fail visibly before downstream modeling or portfolio results are produced.

**Review And Provenance**
- R15. Run metadata or artifacts must record the authored array declaration and the effective expanded array set.
- R16. Reviewers must be able to compare configured arrays, component-required arrays, and loaded data arrays without inspecting component code.
- R17. Removing the old feature-map behavior must be treated as a forward contract change, not a compatibility shim.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R4, R15.** Given a config declares OHLCV, when the run is validated, the effective array set is Open, High, Low, Close, and Volume and that expanded set is visible in run evidence.
- AE2. **Covers R3, R4, R10.** Given a config declares OHLCV plus FundingRate, when data is loaded from a provider that exposes FundingRate as a VBT feature, components can request FundingRate through the same data-array contract.
- AE3. **Covers R6, R7, R8.** Given a selected indicator declares High, Low, and Close as inputs but the config declares only Close, when validation runs, the run fails before executing the indicator.
- AE4. **Covers R10, R11, R17.** Given local CSV data has non-VBT column names, when a run tries to rely on config-level feature mapping, the config is rejected rather than silently remapping columns.
- AE5. **Covers R12, R13, R14.** Given a configured array is unavailable or non-numeric in the loaded VBT data, when data quality validation runs, the run fails before labels, indicators, models, or portfolios are produced.
- AE6. **Covers R15, R16.** Given a completed run, when a reviewer inspects artifacts, they can see the declared arrays, expanded arrays, component-required arrays, and loaded arrays that shaped the result.

---

## Success Criteria

- Experiment authors can state a run's raw data dependency in one visible place without learning provider-specific alias behavior.
- Component authors can add indicators that require non-OHLCV VBT arrays without changing the runner's fixed bundle shape.
- Runs fail before execution when selected components and configured arrays disagree.
- Reviewers and agents can audit data dependencies from config and artifacts rather than reverse-engineering them from code.
- A planner can implement the contract without inventing naming rules, shortcut semantics, feature-map compatibility, or validation timing.

---

## Scope Boundaries

- No generic config-level feature-map or column-renaming DSL.
- No provider-specific alias language in run configs.
- No implicit inference of all required arrays solely from selected components.
- No per-component parameter passing through run config.
- No backward-compatibility shim for configs that rely on removed feature-map behavior.
- No requirement to support arbitrary local CSV columns unless they already expose VBT feature names or are normalized before the run.

---

## Key Decisions

- Use VBT feature names: This keeps the scaffold aligned with VectorBT data semantics instead of creating a parallel naming system.
- Require explicit configured arrays: Explicit run data dependencies are easier to review and less likely to drift when component code changes.
- Allow OHLCV as a mixable shortcut: The common case stays readable while preserving exact expanded dependencies.
- Remove feature_map: Source-specific naming belongs before or inside data-source adaptation, not in the experiment contract.
- Validate before execution: Missing data arrays should fail at the config/data boundary, not deep inside indicator or strategy code.

---

## Dependencies / Assumptions

- Supported providers or local source adapters can expose requested arrays through VBT feature access.
- Existing components can declare their required inputs without needing run-config parameters.
- Existing documentation that mentions feature mapping will need to be updated or superseded by this contract.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R2, R3][Technical] Define the exact authored syntax for scalar OHLCV, mixed array lists, and expanded run evidence.
- [Affects R10, R12, R14][Needs research] Verify how each supported VBT provider exposes non-OHLCV arrays and what failures look like when a requested feature is missing.
- [Affects R15, R16][Technical] Decide where the authored array declaration, expanded array set, component-required arrays, and loaded arrays should appear in artifacts.

---
date: 2026-05-17
topic: vectorbt-indicator-contract
---

# VectorBT Indicator Contract

## Summary

Make indicator generation VectorBT-first: preserve native indicator objects, parameter levels, outputs, and diagnostics through feature generation and artifacts, then derive sklearn-ready feature matrices only at the modeling boundary. Built-in VectorBT indicators and trusted custom VectorBT indicators should share one contract for inputs, params, outputs, feature lineage, warmup diagnostics, and artifact metadata.

---

## Problem Frame

`research/aegis_research/indicators.py` defines the model input contract. The current implementation produces a useful flat-ish feature panel, but it collapses important VectorBT semantics too early: `MA` and `RSI` are run per window with hidden parameter levels, derived transforms are mixed with native outputs, and the returned metadata does not preserve enough lineage for audit, reproducibility, or future feature expansion.

This matters because indicators sit between market data and every downstream model, validation split, signal, portfolio, metric, and report. If the indicator boundary loses parameter identity, output identity, symbol identity, warmup behavior, or native VectorBT object state before artifacts are recorded, later stages can look reproducible while depending on ad hoc column naming and implicit transform rules.

The project is already moving toward VectorBT-native data and provenance contracts. Indicator generation should follow the same direction: VectorBT objects remain the source of truth until the model-input boundary, while sklearn receives an intentional derived view with reversible lineage back to the native hierarchy.

---

## Actors

- A1. Experiment author: Selects built-in or registered custom indicators, parameter grids, and model-facing transforms in experiment config.
- A2. Experiment runner: Builds indicators, records artifacts, and needs failures, warmup behavior, feature identity, and scale risks to be explicit.
- A3. Model training stage: Consumes a flat sklearn-compatible matrix without needing to understand VectorBT internals.
- A4. Run reviewer or automation agent: Inspects artifacts and metadata to understand which data, indicator definitions, params, outputs, transforms, and symbols produced model features.
- A5. Custom indicator author: Adds reusable project-specific indicators while staying inside VectorBT's indicator model.

---

## Key Flows

- F1. Build built-in indicator features
  - **Trigger:** A validated experiment config requests built-in indicators such as moving average or RSI across one or more params and symbols.
  - **Actors:** A1, A2, A3, A4
  - **Steps:** Resolve the configured indicator definitions, run VectorBT indicators with visible parameter identity, preserve native indicator objects and outputs, derive model-facing features, record lineage and diagnostics, and hand sklearn only the derived matrix.
  - **Outcome:** Model features are usable by sklearn while remaining traceable to native VectorBT indicator state.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11
- F2. Build registered custom indicator features
  - **Trigger:** A validated experiment config references a trusted project-registered custom indicator id and supplies supported params.
  - **Actors:** A1, A2, A3, A4, A5
  - **Steps:** Look up the registered VectorBT-compatible indicator definition, validate requested inputs/params/outputs against its declared contract, run it through the same native-first pipeline, and include its outputs in the derived feature matrix with reversible lineage.
  - **Outcome:** Built-in and custom indicators participate in the same artifact, diagnostics, and model-input contract.
  - **Covered by:** R1, R2, R3, R4, R7, R8, R9, R12, R13, R14, R15, R16
- F3. Cross the modeling boundary
  - **Trigger:** Indicator generation is complete and the model stage needs sklearn-compatible input.
  - **Actors:** A2, A3, A4
  - **Steps:** Select eligible model features from native outputs and derived transforms, flatten them deterministically, write a reversible feature-name mapping, apply warmup/NaN policy, verify label/split alignment, and expose the matrix to model training.
  - **Outcome:** sklearn receives a stable matrix, while reviewers can reverse every feature column to native indicator lineage and transform semantics.
  - **Covered by:** R5, R6, R7, R8, R9, R10, R11, R17, R18, R19, R20

---

## Requirements

**Native Indicator Contract**
- R1. Indicator generation must treat native VectorBT indicator objects as first-class stage outputs whenever a feature is produced by a VectorBT indicator.
- R2. Native indicator state must be preserved through feature generation and artifact capture; flattening to sklearn features must happen only at the modeling boundary.
- R3. Built-in indicators and registered custom indicators must expose a common contract for input names, parameter names, output names, selected outputs, parameter values, output transforms, and model-feature eligibility.
- R4. Indicator outputs must preserve visible parameter levels by default; hiding all params must not be the default for outputs that feed artifacts or model features.
- R5. The indicator result must expose both native outputs and model-facing derived features without requiring downstream stages to re-infer indicator semantics from column strings.

**Parameterization And VectorBT Semantics**
- R6. Built-in indicators must use VectorBT parameterization directly, including passing parameter lists to a single indicator run where appropriate rather than looping one parameter value at a time.
- R7. Parameter-grid semantics must distinguish zipped/broadcast parameter lists from Cartesian products, and configs or artifacts must make that distinction visible.
- R8. `run_combs` must be reserved for cases requiring multiple indicator instances, such as fast/slow comparisons; ordinary parameter sweeps must use indicator `run` with parameter lists or equivalent VectorBT parameter-grid mechanisms.
- R9. Meaningful built-in params such as moving-average and RSI `window` and `wtype` must be explicit in the indicator contract rather than hidden behind VectorBT defaults.
- R10. Scale-sensitive runs must expose enough metadata or configuration to reason about grid size, parameter combinations, column expansion, random subset selection when used, execution controls when used, and memory risk.

**Feature Lineage And Model Boundary**
- R11. The sklearn-ready matrix must be a derived view with deterministic feature names and a reversible mapping back to indicator id, native output, parameter values, symbol, and transform semantics.
- R12. Derived feature transforms must be named and documented separately from native indicator outputs, including formulas such as moving-average distance and RSI scaling.
- R13. Primitive transforms such as returns and rolling volatility may remain local Pandas or accessor-backed transforms when they are clearly primitive, but they must still participate in the same feature-lineage, diagnostics, and artifact schema.
- R14. Reusable or domain-specific transforms must have a defined path to graduate into VectorBT `IndicatorFactory` indicators once their params, outputs, diagnostics, or reuse justify first-class indicator status.
- R15. Multi-symbol and single-symbol outputs must preserve stable symbol identity and avoid ambiguous duplicate feature names after flattening.

**Custom Indicator Extension Contract**
- R16. The project must support trusted code-registered custom indicators as first-class indicator definitions, not as ad hoc branches in the indicator builder.
- R17. Registered custom indicators must be VectorBT-compatible: they must provide or wrap a VectorBT indicator class/factory output that exposes input, parameter, output, and run behavior through VectorBT conventions.
- R18. Experiment config must reference registered custom indicators by stable id and supply params; v1 must not execute inline Python snippets or arbitrary formulas from config.
- R19. The custom indicator registry must validate that requested inputs, params, outputs, and model-facing transforms match the registered definition before experiment side effects that depend on those indicators.
- R20. Custom indicators must produce the same lineage, warmup/NaN diagnostics, native-artifact metadata, and sklearn feature mapping as built-in indicators.
- R20a. Custom indicators implemented with VectorBT `IndicatorFactory` must be bar-aligned in v1: each selected output must preserve the input index/symbol shape expected by VectorBT's wrapper model. Shape-changing transforms such as Renko bricks, event lists, compressed bars, trades, or arbitrary objects must not be forced into the indicator stage without a separate non-bar-aligned contract.

**Warmup, NaN Handling, And Alignment**
- R21. Indicator generation must report warmup and missing-value diagnostics per indicator, output, parameter combination, symbol, and derived feature where practical.
- R22. Warmup-row and NaN-handling policy must be explicit before model training and must be applied consistently across built-in indicators, custom indicators, primitive transforms, labels, and validation splits.
- R23. Model input extraction must verify alignment between features, labels, and validation splits after warmup/NaN handling.
- R24. Infinite values from derived transforms must not be silently converted without diagnostics; replacements, drops, or invalid-feature states must be visible in metadata.

**Artifacts, Provenance, And Coverage**
- R25. Indicator artifacts must include portable metadata sufficient to reconstruct feature lineage without loading native artifacts.
- R26. Native VectorBT indicator artifacts must be eligible for private persistence when their semantics would be lost or weakened by portable metadata alone.
- R27. Public artifacts must avoid non-portable absolute paths and must not expose secrets from upstream data-provider or config contexts.
- R28. Tests must cover multiple windows, multiple symbols, visible params, deterministic feature names, reversible feature mapping, warmup/NaN diagnostics, and stable behavior for both built-in and registered custom indicators.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R4, R6.** Given a config requesting MA windows `[10, 30]`, when indicators are built, one native VectorBT MA result preserves visible window identity and artifacts retain native indicator metadata before sklearn flattening.
- AE2. **Covers R7, R8, R10.** Given an indicator with two configurable params, when the config requests zipped params versus a Cartesian product, the resulting parameter combinations and artifact metadata make the chosen grid semantics explicit without using `run_combs` for a normal sweep.
- AE3. **Covers R11, R12, R15.** Given multi-symbol MA distance and RSI features, when sklearn feature names are generated, each flattened name reverses to indicator, output, params, symbol, and transform metadata.
- AE4. **Covers R16, R17, R18, R19, R20.** Given a registered custom indicator id and valid params, when an experiment runs, the indicator is resolved through the trusted code registry, validated against its contract, run as a VectorBT-compatible indicator, and included in the same lineage and diagnostics as built-ins.
- AE5. **Covers R18, R19.** Given config that attempts to define inline Python for an indicator, when validation runs, it fails before indicator execution and explains that custom indicator code must come from the trusted registry.
- AE6. **Covers R21, R22, R23, R24.** Given indicators with different warmup lengths and a derived transform that can produce infinite values, when model input is extracted, warmup/NaN/inf handling is reported and feature-label-split alignment is verified before training.
- AE7. **Covers R25, R26, R27.** Given a completed run with built-in and custom indicators, when artifacts are inspected, public metadata explains feature lineage and native artifact roles without requiring absolute local paths or private state exposure.
- AE8. **Covers R28.** Given test fixtures with multiple windows, multiple symbols, and one registered custom indicator, when tests run, they verify feature identity and reversible mapping rather than only numeric output values.

---

## Success Criteria

- Experiment authors can configure built-in and trusted custom indicators through one coherent VectorBT-first contract.
- Model training still receives a straightforward sklearn-compatible matrix, but that matrix is no longer the only surviving representation of indicator state.
- Run reviewers and automation can trace every model feature back to its native indicator output, parameter values, symbol, and transform semantics.
- Warmup, missing-value, infinite-value, and alignment behavior is explicit before model training.
- Custom indicators can be added as trusted project code without turning experiment config into an arbitrary code execution surface.
- A planner can translate this into implementation work without inventing the indicator boundary, custom-indicator scope, feature-lineage expectations, or success criteria.

---

## Scope Boundaries

- No requirement to carry native VectorBT indicator objects beyond the modeling input boundary into sklearn internals or validation algorithms.
- No inline Python snippets, arbitrary formulas, or untrusted code execution in experiment config for v1 custom indicators.
- No broad public plugin marketplace, package-entry-point discovery system, or third-party extension ecosystem in this issue.
- No requirement to convert every primitive Pandas transform into a custom VectorBT indicator immediately.
- No requirement to support shape-changing custom indicators in v1; non-bar-aligned transforms belong in a separate pipeline such as `vbt.parameterized` or future feature contract work.
- No requirement to design the full large-scale optimization system now; this issue must expose grid and scale semantics but can defer exact chunking/execution architecture to planning.
- No backward compatibility shims for the current lossy indicator output contract; the project can move forward-first while there are no established consumers.
- No requirement that portable metadata replace native VectorBT persistence where native state materially affects reproducibility.

---

## Key Decisions

- VectorBT-first indicator boundary: Native indicator objects and hierarchy remain authoritative until model-input extraction.
- Modeling boundary: sklearn receives a derived flat matrix plus reversible lineage, not native objects directly.
- Shared built-in/custom contract: Registered custom indicators must look like VectorBT indicators to the rest of the pipeline.
- Trusted code registry: Custom indicator definitions live in project code and are referenced by stable id from config.
- Project registry is authoritative: Experiment config resolves indicator ids through a project-owned registry that stores the VectorBT indicator class plus project metadata for selected outputs, transforms, eligibility, diagnostics, and lineage. VectorBT's global `vbt.IF.register_custom_indicator` registry may be used as an optional notebook/Data.run convenience mirror, but it is not the experiment contract.
- Custom indicator construction default: Use `IndicatorFactory.with_apply_func` for first-class project custom indicators because it preserves VectorBT inputs, params, outputs, run behavior, parameter iteration, and output concatenation with minimal custom code. Reserve `with_custom_func` for unusual indicators that need custom concatenation, access to all parameter combinations at once, or output control beyond the apply-function path.
- IndicatorFactory shape discipline: Use `IndicatorFactory` only for custom indicators whose outputs align to the input wrapper shape. If a transform naturally changes row count or returns events/objects, it should not enter this v1 indicator contract.
- Direct class runs as the canonical stage path: Built-in and custom indicators should be run through their indicator classes via `.run(...)` in the stage builder. Avoid making `Data.run(..., concat=True)` the authoritative artifact path because mixed indicators can produce incompatible column levels and push callers toward `hide_params=True`, which conflicts with feature lineage.
- No inline code in config: This avoids turning YAML into a code execution surface and keeps custom indicator definitions reviewable and versioned.
- `run_combs` discipline: Use it only when multiple indicator instances are required; normal sweeps use `run` and parameter-grid semantics.
- Primitive transform pragmatism: Keep simple transforms local when appropriate, but require the same lineage and diagnostics and define a path to `IndicatorFactory` when reuse or metadata pressure increases.

---

## Dependencies / Assumptions

- The market-data contract in `docs/brainstorms/2026-05-16-vectorbt-market-data-contract-requirements.md` defines the VectorBT-native data source that indicator generation should consume.
- The provenance contract in `docs/brainstorms/2026-05-16-experiment-provenance-contract-requirements.md` defines the native-artifact and portable-metadata expectations this indicator contract should feed.
- The config contract in `docs/brainstorms/2026-05-16-experiment-config-contract-requirements.md` defines the validated config, passthrough, and redaction boundary this work should reuse.
- Current indicator generation lives in `research/aegis_research/indicators.py`, and current orchestration calls it from `research/aegis_research/experiments.py`.
- VectorBT PRO docs confirm `IndicatorFactory` is the native path for parameterizable and analyzable custom indicators, with `run`, parameter broadcasting, output naming, stats/plots, and artifact-friendly object behavior.
- VectorBT PRO docs confirm `IndicatorFactory.with_apply_func` is the simplest custom-indicator path: the author supplies a function for one parameter combination, and VectorBT handles parameter iteration, output concatenation, and creation of a class with `input_names`, `param_names`, `output_names`, and `.run` behavior. `with_custom_func` is available when lower-level control is required.
- VectorBT PRO support context confirms `IndicatorFactory` outputs must match the input wrapper shape. Shape-changing transforms should use another mechanism, such as a parameterized pipeline, rather than being registered as indicators.
- VectorBT PRO docs and Discord support confirm `vbt.IF.register_custom_indicator` registers indicator classes under custom locations for lookup and `Data.run` convenience. Registration is global mutable state and should not replace a project registry that validates experiment config, selected outputs, transforms, and lineage.
- VectorBT PRO docs and runtime probing confirm direct `.run` calls preserve visible parameter levels when `hide_params=None` and `hide_default=False`; ordinary parameter sweeps should pass parameter lists to `.run`, zipped by default, and use `param_product=True` only when Cartesian grids are requested.
- VectorBT PRO Discord context confirms `Data.run` over multiple indicators can require `hide_params=True` when column level structures differ, which is useful for quick feature engineering but not ideal as the canonical artifact path for this issue because hidden params weaken lineage.
- Runtime probing confirmed that `MA.run` and `RSI.run` expose `input_names`, `param_names`, `output_names`, `level_names`, parameter value lists, visible parameter column levels, and `to_frame()` output-level structure useful for feature lineage.
- Runtime probing confirmed a project custom indicator built with `vbt.IF(...).with_apply_func(...)` exposes the same core metadata and output structure as native indicators, including class `input_names`, `param_names`, `output_names`, visible parameter columns, per-output frames, `to_frame()` output levels, and `config["param_list"]` / `config["mapper_list"]` parameter evidence.
- Project principles in `AGENTS.md` favor forward-first contracts, fail-fast validation, explicit errors, and no silent error swallowing.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R3, R16, R17][Resolved by research] Use a project-owned registry of indicator definitions as the authoritative experiment contract. Each definition should include a stable id, VectorBT indicator class, declared input names, parameter names, output names, selected outputs, model-facing transforms, eligibility, and default run kwargs. Optionally mirror custom indicators into `vbt.IF.register_custom_indicator(..., location="aegis")` for notebook/Data.run ergonomics, but do not validate or execute experiments from VectorBT's global mutable registry alone.
- [Affects R11, R12, R15][Technical] What deterministic flat feature-name encoding should be used, and how should the reversible mapping be serialized?
- [Affects R21, R22, R23, R24][Technical] What first-version warmup/NaN/inf policy should be applied before model training?
- [Affects R10][Needs research] Which VectorBT execution, chunking, caching, or random-subset controls should be surfaced in v1 config versus deferred until large grids require them?
- [Affects R25, R26][Technical] Which native indicator artifacts must be persisted privately, and what portable summaries are sufficient for automation?

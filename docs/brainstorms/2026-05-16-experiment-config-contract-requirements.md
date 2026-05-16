---
date: 2026-05-16
topic: experiment-config-contract
---

# Experiment Config Contract

## Summary

Harden experiment configuration into a first-class public contract before the research scaffold has real consumers. The contract should validate configs before experiment side effects, make invalid input actionable, model safe provider and credential boundaries, and preserve reproducible redacted config evidence in run artifacts.

---

## Problem Frame

Experiment YAML is currently the main authoring surface for research runs. In the current scaffold, YAML is loaded directly into frozen dataclasses in `research/aegis_research/config.py`, while several invalid values are only discovered later by the module that happens to use them.

That keeps early scaffolding small, but it makes the config boundary too implicit for a public experiment contract. Unknown fields can surface as raw constructor errors, enum-like strings are not centrally described, cross-field requirements are scattered, and saved config artifacts do not yet establish exactly which raw and resolved values governed a run.

Because the project is still being built and has no compatibility burden yet, this is the right moment to define the stricter contract forward-first rather than preserve permissive behavior.

---

## Actors

- A1. Config author: Writes or edits experiment YAML and needs fast, actionable feedback.
- A2. Experiment runner: Starts experiments and needs validation to happen before data fetches, artifact writes, or expensive work.
- A3. Run reviewer: Inspects completed run artifacts and needs resolved, redacted config evidence.
- A4. Automation or agent: Generates, validates, or compares configs and needs stable machine-readable failure shape and artifact semantics.

---

## Key Flows

- F1. Validate before run
  - **Trigger:** A config is loaded for an experiment run.
  - **Actors:** A1, A2, A4
  - **Steps:** Parse the YAML, apply defaults intentionally, validate types and known fields, validate allowed values, validate cross-field rules, then either return a resolved config or a structured validation failure.
  - **Outcome:** Invalid configs fail before experiment side effects; valid configs are safe for downstream modules to trust.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12
- F2. Preserve run config evidence
  - **Trigger:** A validated experiment writes run artifacts.
  - **Actors:** A2, A3, A4
  - **Steps:** Record schema version, raw-config identity, resolved/default-applied config, and public-safe redacted values in the run output.
  - **Outcome:** Reviewers and automation can tell what contract version and effective config governed the run without exposing secrets.
  - **Covered by:** R13, R14, R15, R16

---

## Requirements

**Validation Boundary**
- R1. Config validation must complete before any experiment side effects, including data fetches, artifact writes, model training, or report generation.
- R2. Validation failures must identify the relevant config path and provide an actionable message suitable for a config author or automation.
- R3. Unknown fields must fail fast unless they appear inside explicitly designated passthrough areas for provider or execution options.
- R4. Wrong scalar, list, mapping, and null shapes must fail without broad implicit coercion; absence is allowed only where the contract defines a meaningful default or optional value.

**Allowed Values And Ranges**
- R5. Enum-like config fields must have centrally enforced allowed values for data source, label kind and mode, split kind, model kind, portfolio size type, portfolio direction, and report gate comparator/status semantics introduced by the contract.
- R6. Numeric and collection bounds must be validated centrally for values such as windows, thresholds, fees, slippage, row counts, sample counts, split sizes, embargo bars, and validation split counts.

**Cross-Field Rules**
- R7. Source-specific config requirements must be enforced at load time, including required file path for CSV configs and required provider parameters for remote data sources.
- R8. Label-specific requirements must be enforced at the config boundary where they can be known before execution, including high/low-data requirements for label kinds that depend on high and low prices.
- R9. Split and signal consistency rules must be enforced centrally, including valid train-size ranges, rolling split minimums, non-empty expected split shape, and threshold relationships that would otherwise produce ambiguous signals.
- R10. Report gates that depend on annualized or frequency-sensitive metrics must require an explicit frequency assumption or source before they are treated as contractually valid.

**Provider Options And Secrets**
- R11. Provider-specific public options and generic execution options must be modeled as explicit passthrough areas rather than accepted as arbitrary top-level fields.
- R12. Secret values must have a defined boundary that prevents committed inline credentials from becoming part of public experiment configs or persisted public artifacts.
- R13. Any serialized config or manifest output must redact secret-sensitive fields using contract-defined matching rules for credential-like names.

**Versioning And Artifacts**
- R14. The config contract must include a top-level schema version and a forward-first evolution policy for breaking or removing fields while no persisted consumer compatibility is required.
- R15. Run artifacts must include enough config evidence to distinguish raw author input from resolved/default-applied values.
- R16. Run artifacts must include a stable raw config identity suitable for comparing whether two runs came from the same authored input.

**Fixtures And Coverage**
- R17. Existing baseline experiment configs must remain valid fixtures under the hardened contract unless the requirements intentionally tighten them.
- R18. Invalid fixture coverage must include unknown fields, wrong types, bad enum values, invalid numeric bounds, bad thresholds, missing CSV path, invalid split settings, invalid label settings, and secret-redaction behavior.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given a config with an unexpected field in a known section, when validation runs, it fails before creating a run directory and reports the offending config path.
- AE2. **Covers R4, R5, R6.** Given a config with a string where a list is required or an unsupported enum-like value, when validation runs, it fails with an actionable path-aware validation error rather than coercing or failing later.
- AE3. **Covers R7.** Given a CSV data-source config without a data path, when validation runs, it fails at config load time rather than when market data loading begins.
- AE4. **Covers R8.** Given a label kind that requires high and low prices but a data contract that cannot provide them, when validation can determine that mismatch before execution, it fails at the config boundary.
- AE5. **Covers R9.** Given a rolling split with too few splits or an invalid train-size range, when validation runs, it fails centrally before split construction.
- AE6. **Covers R12, R13.** Given a config containing credential-like provider values, when validation or artifact serialization handles it, inline committed secrets are rejected or redacted according to the contract.
- AE7. **Covers R14, R15, R16.** Given a successful run, when a reviewer inspects artifacts, they can see schema version, raw config identity, and resolved config values without exposing secret material.

---

## Success Criteria

- Config authors get fast, path-specific feedback for invalid experiment YAML before any expensive or persistent experiment work starts.
- Downstream experiment modules can assume they receive validated config values and do not need to duplicate public-contract checks.
- Run artifacts make the effective config understandable and comparable while keeping secrets out of public outputs.
- A planner can translate the requirements into implementation work without inventing config behavior, scope boundaries, or success criteria.

---

## Scope Boundaries

- No backward compatibility shims for old configs or persisted runs; the project has no current consumers requiring that carrying cost.
- No new data-provider capability is required beyond defining how provider-specific public options, execution options, and secrets enter the config contract.
- No requirement to choose a validation library, dataclass architecture, exact error class design, artifact filenames, or hash algorithm in this brainstorm.
- No broad permissive coercion layer intended to make loosely written YAML work; strict, explicit config remains the target.
- No attempt to make every possible VectorBT option first-class in the top-level schema; explicit passthrough areas are the boundary for provider-specific expansion.

---

## Key Decisions

- Full issue scope: Treat validation, versioning, provider/secret boundaries, redaction, hashing, and artifact semantics as one cohesive config-contract hardening feature.
- Forward-first contract: Since nothing is yet used, prefer strict future-facing behavior over compatibility and migration paths.
- Centralized public validation: Downstream modules may still defend their own invariants, but user-facing config validity belongs at the config boundary.
- Explicit passthrough areas: Unknown fields remain errors unless the contract names a safe place where passthrough provider or execution options are allowed.
- Artifact evidence matters: The run output should preserve both authored-input identity and resolved/default-applied config meaning.

---

## Dependencies / Assumptions

- The current baseline configs in `research/configs/experiments/` are the initial positive fixtures for the contract.
- The current downstream checks in `research/aegis_research/data.py`, `research/aegis_research/labels.py`, `research/aegis_research/splits.py`, and `research/aegis_research/portfolios.py` reflect known implicit contract rules to centralize.
- VectorBT-facing values should remain understandable at the scaffold boundary, even if planning later chooses whether to normalize them as strings or native constants internally.
- The project prefers fail-fast, explicit errors, and forward-first evolution per `AGENTS.md`.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Technical] What typed error structure best balances human-readable path messages with machine-readable automation needs?
- [Affects R5][Needs research] Which VectorBT portfolio and label values should be accepted exactly in the first schema version?
- [Affects R10][Technical] Which frequency source should annualized report gates use when data providers and synthetic data can express time differently?
- [Affects R12, R13][Technical] What exact secret-detection and redaction rules should be enforced for nested provider and execution options?
- [Affects R15, R16][Technical] What artifact shape and raw config identity algorithm should planning choose for reproducibility and comparison?

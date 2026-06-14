---
date: 2026-05-16
topic: experiment-provenance-contract
---

# Experiment Provenance Contract

## Summary

Make each experiment run a machine-readable, reproducible provenance record. The contract should preserve native VectorBT state where it matters, pair every material artifact with portable manifest metadata, make rerun intent explicit, preserve failed-run evidence, and treat walk-forward validation splits as first-class artifact sets rather than hiding them behind aggregate outputs.

---

## Problem Frame

`research/aegis_research/experiments.py` is the top-level research pipeline: data loading, OHLC extraction, indicators, labels, splits, validation, report generation, and artifact writing all converge there. That makes it the natural boundary where a run becomes more than a sequence of computations: it becomes evidence that can be compared, checked, and replayed later.

The current scaffold writes useful inspection artifacts, including resolved config outputs, report JSON, probabilities, signals, split metrics, and a model artifact. It also currently collapses important provenance: VectorBT objects are converted to plain Pandas objects early, only a small config manifest is written, and walk-forward validation exports the last trained model in a way that can look canonical even though predictions may come from multiple split-specific models.

Because this project is still being built, there is no compatibility burden that requires preserving weak artifact semantics. The right moment to define a strict provenance contract is before real research runs create historical outputs that downstream tools, agents, or humans start relying on.

---

## Actors

- A1. Experiment runner: Starts a research run and needs deterministic, non-ambiguous run identity and lifecycle behavior.
- A2. Automation agent or CI: Reads run artifacts to validate determinism, compare runs, detect missing evidence, and reject incomplete or inconsistent outputs.
- A3. Run reviewer: Inspects a run later and needs to understand what happened without guessing from loose files.
- A4. Future maintainer: Evolves the scaffold and needs stable artifact contracts instead of implicit stage coupling.

---

## Key Flows

- F1. Start a new run
  - **Trigger:** A validated experiment config is submitted for execution.
  - **Actors:** A1, A2
  - **Steps:** Resolve run identity, capture config evidence, capture environment and repository evidence, initialize run status, create the run record, and begin stage execution only after the run record can track provenance.
  - **Outcome:** The run has a durable identity and a manifest that can record every later artifact and stage state.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11
- F2. Produce stage artifacts
  - **Trigger:** A pipeline stage produces data, indicators, labels, splits, models, signals, portfolios, metrics, or reports.
  - **Actors:** A2, A3, A4
  - **Steps:** Persist required native VectorBT state when the artifact contains material VectorBT semantics, write portable metadata for the artifact, record schema/version/hash/shape/provenance in the manifest, and link derived artifacts back to their inputs.
  - **Outcome:** Automation can validate artifact completeness and lineage without loading version-sensitive binaries, while native state remains available for same-environment recomputation.
  - **Covered by:** R12, R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R23, R24, R25, R26, R27
- F3. Complete, fail, or rerun
  - **Trigger:** A run finishes successfully, raises during execution, or encounters an existing run identity/path.
  - **Actors:** A1, A2, A3
  - **Steps:** Record terminal status, timestamps, completed stages, failed stage diagnostics, artifact inventory, and explicit rerun mode when applicable.
  - **Outcome:** Completed and failed runs remain auditable; accidental overwrite, resume, or duplicate interpretation cannot happen silently.
  - **Covered by:** R3, R4, R5, R6, R28, R29, R30, R31

---

## Requirements

**Run Identity And Lifecycle**
- R1. Every experiment run must produce a run manifest that is the machine-readable source of truth for run identity, status, timestamps, config evidence, environment evidence, stage records, artifact inventory, and lineage.
- R2. Run identity must include a human-distinguishable run label and deterministic fingerprints sufficient to compare whether two runs came from the same effective inputs.
- R3. New immutable run records must be the default behavior for normal execution.
- R4. If a run identity or output path collision occurs, execution must fail by default rather than silently overwriting, resuming, or merging artifacts.
- R5. Any non-default rerun behavior, including overwrite, resume, fork, or duplicate-new-run intent, must be explicit before execution and recorded in the manifest.
- R6. The manifest must distinguish lifecycle states such as running, completed, failed, and interrupted or killed when that distinction is observable.

**Config, Environment, And Repository Evidence**
- R7. The manifest must record raw authored config identity, resolved/default-applied config identity, redacted config evidence, and the config contract version that governed the run.
- R8. The manifest must record reproducibility-relevant environment evidence, including Python, platform, project package identity when available, VectorBT PRO, pandas, NumPy, scikit-learn, Numba, joblib, and other packages that materially affect execution.
- R9. The manifest must record repository evidence when available, including commit, branch, dirty status, and remote identity, without failing runs that execute outside a Git checkout.
- R10. The manifest must record seed policy and all run-level seeds that materially affect Python, NumPy, Numba, VectorBT, model training, synthetic data, or stochastic validation behavior.
- R11. The manifest must record relevant VectorBT settings or setting overrides that can affect data handling, portfolio behavior, returns/stats, jitting, chunking, caching, or persistence.

**Artifact Contract**
- R12. Every artifact recorded in the manifest must include a stable artifact id, artifact type, producer stage, source config section or upstream dependency, schema version, path or storage reference, content hash, size, row/column or object shape when applicable, and creation status.
- R13. Artifacts that summarize or derive from other artifacts must link back to the exact upstream artifact ids they used.
- R14. Portable structured artifacts and metadata must be sufficient for automation to validate completeness, lineage, identity, schemas, and hashes without loading native binary artifacts.
- R15. Native VectorBT persistence is required for material VectorBT objects whose semantics would be lost or weakened by flattening to CSV/JSON alone.
- R16. Each native VectorBT artifact must be paired with portable metadata that records compatible-version expectations, object role, object class/type identity, producer stage, and enough shape/summary information for validation without loading it.
- R17. Version-sensitive native artifacts must never be the sole source of deterministic evidence for a run.
- R18. Public artifact outputs must redact or exclude secret-sensitive config values, provider credentials, tokens, and credential-like nested options by default.

**Stage Provenance**
- R19. Data provenance must preserve data-provider metadata that materially affects reproducibility, including provider/fetch parameters, returned provider metadata, symbol coverage, last index or range evidence, delisted flags when available, timezone policy, missing-index policy, missing-column policy, wrapper metadata, and raw data identity.
- R20. Indicator provenance must preserve enough metadata to reconstruct which inputs, windows, parameters, and column meanings produced each indicator artifact.
- R21. Label provenance must preserve native label kind, label mode, horizon/threshold settings, required OHLC inputs, derived target conversion, and missing-label handling.
- R22. Split provenance must preserve exact train/test membership or bounds, split labels, index ranges, purging or embargo settings, and any prediction/evaluation-time assumptions.
- R23. Model, signal, portfolio, metrics, and report provenance must preserve stage inputs, parameters, artifact links, and schema versions so each downstream output can be traced to the stage evidence that produced it.

**Walk-Forward Semantics**
- R24. Walk-forward validation must treat each split as a first-class child artifact set with its own model artifact, probability output, signal output, train/test portfolio evidence, metrics, split bounds, and metadata.
- R25. Aggregate probabilities, signals, metrics, portfolios, or reports must be represented as derived artifacts that link back to the split artifact ids they summarize.
- R26. A single top-level model artifact must not imply deployment readiness or canonical experiment output for multi-split validation unless the run mode explicitly produced a single deployable model.
- R27. Probability and signal outputs for split-based validation must preserve split and set identity clearly enough that automation can identify which model and index window produced each value.

**Failure And Diagnostics**
- R28. If a run fails after a run record is initialized, the run evidence must be preserved with failed status rather than silently cleaned up.
- R29. Failed-run manifests must record completed stages, skipped or incomplete stages, partial artifacts, failed stage identity, redacted diagnostic details, and terminal timestamp.
- R30. Partial artifacts must be marked as partial, failed, or incomplete when they cannot satisfy the normal artifact contract.
- R31. Artifact cleanup or garbage collection must be explicit future behavior, not the default response to run failure.

**Orchestration Boundaries**
- R32. Experiment orchestration must not depend on private helpers from unrelated pipeline stages for shared data-shape concerns.
- R33. Primary OHLC selection must be owned by a data/schema boundary rather than imported from label internals.
- R34. Pipeline stages must expose enough structured result metadata for orchestration to build the manifest without re-inferring each stage's internal semantics.
- R35. The provenance contract must fail fast on stage contract violations that would make a run unauditable or artifact lineage incomplete.

---

## Acceptance Examples

- AE1. **Covers R1, R7, R12.** Given a successful experiment run, when automation reads the manifest, it can identify the run, config evidence, artifact list, schema versions, hashes, producer stages, and artifact statuses without opening any binary artifact.
- AE2. **Covers R3, R4, R5.** Given an output collision with an existing run record, when no explicit rerun mode is supplied, execution fails before modifying the existing run evidence.
- AE3. **Covers R8, R9, R10, R11.** Given a completed run, when a reviewer or agent compares it to another run, the manifest exposes environment, repository, seed, and VectorBT settings evidence needed to explain whether the runs are comparable.
- AE4. **Covers R15, R16, R17.** Given a run that produces material VectorBT data or portfolio state, when artifacts are written, the native VectorBT artifact is persisted and paired with portable metadata that remains useful even if the native artifact cannot be loaded in a future package version.
- AE5. **Covers R19, R20, R21, R22, R23.** Given any pipeline stage output, when the manifest is inspected, the output can be traced to its source inputs, config section, stage parameters, and upstream artifact ids.
- AE6. **Covers R24, R25, R26, R27.** Given a walk-forward validation run with multiple splits, when artifacts are inspected, each split has its own model/probability/signal/portfolio/metric evidence and no single last model is presented as the canonical experiment model.
- AE7. **Covers R28, R29, R30, R31.** Given a run that fails after creating data and indicator artifacts but before report generation, when the run directory is inspected, the manifest records failed status, completed stages, partial artifact state, and redacted diagnostics instead of deleting the evidence.
- AE8. **Covers R18.** Given provider options containing credential-like keys or values, when manifest and artifact metadata are written, secret-sensitive values are redacted or excluded by default.
- AE9. **Covers R32, R33, R34, R35.** Given orchestration needs primary OHLC data and stage metadata, when planning implements the contract, those concerns are exposed through data/schema and stage-result boundaries rather than private helpers in unrelated modules.

---

## Success Criteria

- Automation can validate a completed or failed run's provenance, artifact completeness, hashes, stage lineage, and schema versions from the manifest and portable metadata.
- A future runner can distinguish fresh, duplicate, resumed, overwritten, forked, completed, failed, and partial runs without relying on folder timestamps or filename conventions alone.
- Walk-forward validation artifacts no longer imply that the last trained model is the canonical experiment output.
- Native VectorBT state needed for faithful same-environment recomputation is preserved, while deterministic comparison does not depend on unpickling version-sensitive binaries.
- A planner can translate the contract into implementation work without inventing run lifecycle behavior, artifact semantics, split semantics, failure policy, or provenance success criteria.

---

## Scope Boundaries

- No full W&B, MLflow, or DVC replacement is required; the feature is a local scaffold provenance contract, not a hosted experiment-tracking product.
- No requirement to choose exact filenames, directory layout, class names, schema serialization format, hash algorithm, storage backend, or stage-result architecture during brainstorming.
- No backward compatibility shims are required for previous scaffold outputs because the project has no real historical consumers yet.
- No requirement to make native VectorBT artifacts stable across incompatible Python or VectorBT versions; the contract records compatibility expectations and provides portable metadata alongside them.
- No default artifact cleanup on failure; cleanup and retention policy can be designed later as explicit behavior.
- No deployment-model registry semantics are implied by experiment model artifacts.
- No human-first reporting UI is required beyond concise summaries and readable structured artifacts.

---

## Key Decisions

- Full provenance contract: Preserve the issue's broad scope rather than cutting to a minimal manifest-only slice.
- Machine-readable first: Optimize for determinism, CI/agent validation, and reliability; human readability is secondary.
- Strict hybrid artifacts: Require native VectorBT persistence for material objects and portable manifest metadata for deterministic validation.
- Immutable by default: Normal runs create new records; collision, resume, overwrite, and fork paths require explicit recorded intent.
- Preserve failed evidence: Failed runs keep status, partial artifact inventory, completed-stage evidence, and redacted diagnostics.
- Split-first validation: Walk-forward splits are first-class child artifact sets; aggregate reports are derived summaries.
- Forward-first contract: Prefer strict future-facing semantics over permissive behavior while the scaffold is still pre-consumer.

---

## Dependencies / Assumptions

- The existing config-contract requirements in `docs/brainstorms/2026-05-16-experiment-config-contract-requirements.md` define the validated config boundary this provenance contract should consume, not duplicate.
- Current orchestration in `research/aegis_research/experiments.py` is the verified top-level run boundary for this work.
- Current validation behavior in `research/aegis_research/validation.py` returns only the last trained model plus aggregate outputs, so split-level artifact semantics need to be made explicit.
- Current config handling in `research/aegis_research/config.py` already includes redacted authored/resolved config evidence and a small config manifest, which this work should integrate into the broader run manifest.
- VectorBT PRO persistence is appropriate for material native state but remains version-sensitive; portable metadata is required to keep run validation reliable without native loading.
- The project principles in `AGENTS.md` favor fail-fast behavior, explicit error types, no silent error swallowing, and forward-first contracts.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R12][Technical] What exact manifest schema versioning shape, artifact id format, and schema validation mechanism should implement the contract?
- [Affects R2, R4, R5][Technical] What concrete run identity fields and collision detection rules best balance readable run labels with deterministic fingerprints?
- [Affects R8, R11][Needs research] Which VectorBT settings and package versions materially affect this scaffold's outputs and must be captured in the first contract version?
- [Affects R15, R16][Needs research] Which exact objects produced by the current pipeline qualify as material VectorBT objects requiring native persistence?
- [Affects R19, R23][Technical] What compact metadata summaries should be recorded for large data, indicator, signal, and portfolio artifacts without duplicating heavy payloads in the manifest?
- [Affects R28, R29, R30][Technical] What diagnostic fields can be safely recorded for failed runs while preserving redaction and avoiding secret leakage?
- [Affects R32, R33, R34][Technical] What stage-result boundary should planning introduce so orchestration can build provenance without knowing every stage's internals?

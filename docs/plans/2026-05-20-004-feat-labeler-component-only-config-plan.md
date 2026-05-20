---
title: feat: Make Labelers Component-Only Config
type: feat
status: completed
date: 2026-05-20
origin: docs/brainstorms/2026-05-20-label-component-only-contract-requirements.md
---

# feat: Make Labelers Component-Only Config

## Summary

Move train label selection to a top-level `labeler` ID-only mapping, make it mutually exclusive with top-level `strategy`, and narrow active playbook support to indicator and strategy research sweeps. Label behavior remains fixed in reviewed component source, while config validation, train execution, artifacts, docs, fixtures, and tests converge on the component-only labeler contract.

---

## Problem Frame

The current implementation already executes train labels through reviewed label components, but the config and registry surfaces still expose a broader generic source-ref shape. That keeps stale label playbook/playground semantics alive even though the product intent is now a fixed labeler component for training and separate strategy playbooks for research sweeps.

---

## Requirements

**Label source boundary**
- R1. Training labels must be an active component-only contract; label playbooks, label playgrounds, and label sweeps must not remain supported executable train-label sources. Origin: R1, F1, F3, AE2.
- R2. Train-mode labeler selection must live at the top level as an ID-only mapping; the component source kind is implied and should not be authored as a label source discriminator. Origin: R2, F1, AE1.
- R3. Label generator params, target selection, target transforms, output declarations, and split-safety assumptions must be fixed in reviewed label component source rather than supplied by train YAML. Origin: R3, F2, AE3.
- R4. Label component source must remain reviewable and manually configurable through the existing Python percent-cell component style. Origin: R4, F2, AE3.

**Validation and failure behavior**
- R5. Config validation must fail fast when a train config attempts to use a label playbook, label playground path, label sweep axis, inline label code, or label params outside the selected component. Origin: R5, F1, F3, AE1, AE2.
- R6. Removing `source` from label selection must be treated as a forward contract cleanup, not as a compatibility layer that silently accepts multiple old label shapes. Origin: R6, AE2.
- R7. The existing native label-building behavior may remain available to label components, but it must not expose label sweep authoring as a public train-config surface. Origin: R7, F2, AE3.

**Docs, examples, and consistency**
- R8. Public docs and examples must describe labels as fixed reviewed components for train mode and avoid suggesting that labels participate in the playbook sweep lane. Origin: R8, F3, AE4.
- R9. Indicator and strategy playbooks must remain explicitly allowed for research sweeps; this cleanup is label-specific and must not weaken composed indicator/strategy candidate semantics. Origin: R9, F3, AE4.
- R10. Run and train artifacts must remain understandable to reviewers: label evidence should point back to the fixed selected component, not to hidden config params or stale playground state. Origin: R10, AE5.
- R11. Configs must keep top-level labeler/train selection and top-level strategy/run selection mutually exclusive: if a strategy source is present, labeler selection must be absent; if a labeler is present, strategy selection must be absent. Origin: R11, F1, AE6.

**Origin actors:** A1 Config author, A2 Label component author, A3 Training runner, A4 Reviewer or automation agent
**Origin flows:** F1 Select a training label, F2 Author a fixed label component, F3 Clean up stale labeler surface
**Origin acceptance examples:** AE1 ID-only top-level labeler mapping, AE2 stale label playbook/playground rejection, AE3 component-source params, AE4 docs/source-mode clarity, AE5 artifact traceability, AE6 labeler/strategy exclusivity

---

## Scope Boundaries

- No replacement labeler playground or UI.
- No train-config label params, formulas, inline Python, notebook paths, arbitrary script paths, or sweep axes.
- No automatic generation or promotion of label components.
- No compatibility shim for old label playbook, playground, nested `train.label`, or label-source config shapes.
- No changes to indicator or strategy playbook sweep semantics beyond removing label-related confusion.
- No expansion of model families, target kinds, or split-validation support as part of this cleanup.
- No migration path for local label playbook `.py` files; the origin scan found no committed label playbook files and the active contract removes that family.

### Deferred to Follow-Up Work

- Broader train-lane naming cleanup: defer any rename of the remaining `train` block beyond removing label selection from it.
- Historical solution-doc rewrites: old `docs/solutions/` examples may mention prior config shapes as historical context and should not be rewritten unless active docs/tests depend on them.

---

## Context & Research

### Relevant Code and Patterns

- `research/aegis_research/configuration/schema.py` owns the public lane dataclasses, `CONFIG_SCHEMA_VERSION`, top-level allowed source constants, and currently models `TrainLaneConfig.label` as a generic `SourceRefConfig`.
- `research/aegis_research/configuration/validation.py` owns strict raw config validation through `_validate_raw_lane_config`, `_validate_train_lane`, `_validate_source_ref`, `_validate_known_keys`, and lane executable-key rejection.
- `research/aegis_research/configuration/builders.py` builds `TrainLaneConfig` and currently reads `train["label"]` through the generic source-ref builder.
- `research/aegis_research/configuration/resolution.py` round-trips raw dicts, lane dataclasses, and resolved configs through validation and redacted authored/resolved config evidence.
- `research/aegis_research/cli_commands/run.py` already loads label components with `ComponentSelection("labels", config.label.id)` and attaches component source metadata to label results.
- `research/aegis_research/experiments.py` uses `config.label.source` only to decide whether label component input arrays should be preflighted; labelers should become unconditionally component-backed in train mode.
- `research/aegis_research/labels.py` preserves native VectorBT label objects, selected target lineage, diagnostics, target schema, split-safety, and evaluation evidence; these helpers should remain available inside label components.
- `research/aegis_research/component_registry/*` keeps labels as a valid component family with percent-cell source, literal manifests, deterministic source hashes, and no discovery-time execution.
- `research/aegis_research/playbook_registry/contracts.py` and `research/aegis_research/playbook_registry/registry.py` still treat `labels` as a playbook family/stage.
- `docs/components.md`, `docs/playbooks.md`, `docs/vectorbt-scaffold.md`, `research/playbooks/labels/README.md`, and train YAML fixtures still expose some old label source or label playbook language.
- `tests/integration/research/aegis_research/test_config_contract.py`, `tests/integration/research/aegis_research/test_lane_config_contract.py`, and `tests/integration/research/aegis_research/test_train_cli.py` are the main config/train contract coverage.
- `tests/unit/research/aegis_research/test_playbooks.py` and `tests/integration/research/aegis_research/test_run_playbook_sources.py` protect playbook registry and run-lane playbook behavior.

### Institutional Learnings

- `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`: lane config loading is a public, schema-versioned, fail-fast boundary with path-aware validation and redacted authored/resolved provenance.
- `docs/solutions/logic-errors/vectorbt-label-contract-target-lineage-2026-05-17.md`: label generation must preserve native VectorBT semantics before deriving model targets; public train YAML selects reviewed label components rather than inline label params.
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md`: removed config fields should remain removed and fail via normal unknown-field validation instead of compatibility branches.
- `docs/solutions/architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md`: configs select reviewed components/plugins, while core Aegis owns target compatibility, probability semantics, and provenance.

### External References

- No external research used. The repo has direct local patterns for config validation, component discovery, playbook discovery, train CLI execution, docs fixtures, and forward-first contract cleanup.

---

## Key Technical Decisions

- Top-level `labeler` mapping: move labeler selection out of `train.label` and into a top-level ID-only mapping so it sits beside `strategy` as the train counterpart and supports precise unknown-key validation.
- Keep `train` for training-only settings: preserve the existing `train` block for model, split, and signals so this plan changes labeler selection without relitigating the rest of train-mode structure.
- Strict exclusivity at validation: a config with both top-level `strategy` and top-level `labeler` is invalid in either lane, preventing the runner from inferring intent.
- Component source remains implied in authored config but explicit in evidence: YAML omits labeler source, while runtime label metadata and artifacts should still identify the selected component and source identity.
- Keep schema version stable for this in-flight contract cleanup: preserve `CONFIG_SCHEMA_VERSION` unless implementation uncovers a repo policy requiring a bump, and rely on field-level validation to make stale shapes actionable.
- Narrow playbook families to indicators and strategies: remove labels from active playbook family/stage declarations while preserving indicator/strategy playbook registry and run-lane semantics.
- No label playbook migration path: the repo has no committed label playbook files, so the plan updates active contracts and docs rather than scanning or migrating absent local files.

---

## Open Questions

### Resolved During Planning

- Should labeler selection be nested under `train.label` or top-level? Use a top-level `labeler` field that is mutually exclusive with top-level `strategy`.
- Should `labeler` be a scalar ID or an ID-only mapping? Use an ID-only mapping so validation can reject `labeler.source`, `labeler.params`, and executable keys at precise paths.
- Should existing lower-level label builders be removed? No. Keep them as component internals; remove only public playbook/playground/sweep/config-param exposure.
- Should local label playbooks be migrated? No. The repo scan found no committed label playbook `.py` files, and the user confirmed there are no label playbooks to preserve.
- Should old `{source: component, id: ...}` labeler config be accepted temporarily? No. The origin requires a forward-first cleanup with no compatibility shim.

### Deferred to Implementation

- Exact class/helper names for the new labeler config object and validator: choose while implementing, keeping the typed shape small and specific to labeler selection.
- Exact validation wording: choose implementation-time messages that are path-specific and actionable without locking the plan to string literals.
- Exact artifact metadata shape for selected label component identity: choose the smallest shape consistent with existing component source identity evidence.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

| Authored shape | Intended lane | Validation outcome |
|---|---|---|
| Top-level `strategy`, no `labeler` | `run` | Valid run-lane strategy selection when other run requirements pass |
| Top-level `labeler`, no `strategy` | `train` | Valid train-lane labeler selection when the ID resolves to a label component |
| Both top-level `strategy` and `labeler` | ambiguous | Invalid before execution |
| Nested train label selection | train legacy | Invalid forward-first stale shape |
| Labeler mapping with `source`, `params`, paths, code, or sweep-like keys | train legacy/unsafe | Invalid before execution |

---

## Implementation Units

### U1. Add Top-Level Labeler Config Contract

**Goal:** Replace nested generic train label source refs with a top-level ID-only labeler mapping and enforce strategy/labeler exclusivity at config validation.

**Requirements:** R1, R2, R5, R6, R11; covers F1, AE1, AE2, AE6.

**Dependencies:** None.

**Files:**
- Modify: `research/aegis_research/configuration/schema.py`
- Modify: `research/aegis_research/configuration/validation.py`
- Modify: `research/aegis_research/configuration/builders.py`
- Modify: `research/aegis_research/configuration/resolution.py`
- Modify: `research/aegis_research/config.py`
- Test: `tests/integration/research/aegis_research/test_config_contract.py`
- Test: `tests/integration/research/aegis_research/test_lane_config_contract.py`

**Approach:**
- Introduce a labeler-specific config type with only a stable component ID instead of reusing the generic source-ref type.
- Update train-lane raw validation so the top-level allowed keys include `labeler`, the train block no longer accepts label selection, and train configs require a valid labeler mapping.
- Add a dedicated labeler validator that accepts only the ID-only mapping, checks the ID shape, rejects `all`, validates against the label component registry, and applies executable-key rejection before any train side effects.
- Extend lane-mode inference and expected-lane validation so `labeler` implies train mode, `strategy` implies run mode, and both together are invalid rather than guessed.
- Preserve existing run-lane strategy and indicator source-ref validation unchanged except for rejecting stray top-level `labeler` in run configs.
- Keep authored and resolved config provenance redaction working after the dataclass shape changes.

**Execution note:** Start with failing config-contract tests for the new accepted shape and the old rejected shapes before changing builders and dataclasses.

**Patterns to follow:**
- Path-aware `ConfigValidationIssue` style in `research/aegis_research/configuration/validation.py`.
- Strict known-key validation and removed-field rejection from existing data-array, signal, and lane config tests.
- Public config re-export pattern in `research/aegis_research/config.py`.

**Test scenarios:**
- Happy path, covers AE1: a train config with top-level `labeler: {id: demo.fixlb}` resolves and selects the known label component.
- Happy path: a run config with top-level `strategy` and no `labeler` still resolves through the existing run lane.
- Error path, covers AE6: a config with both top-level `strategy` and top-level `labeler` fails before execution for both expected run and expected train validation.
- Error path, covers AE2: old `train.label: {source: component, id: demo.fixlb}` fails as a stale nested label selection instead of being accepted as compatibility.
- Error path: `labeler.source`, `labeler.params`, `labeler.path`, `labeler.notebook_path`, `labeler.artifact_path`, `labeler.python`, `labeler.code`, `labeler.formula`, and sweep-like keys fail with paths under `labeler`.
- Error path: missing `labeler` in train mode fails with an actionable config error.
- Error path: unknown labeler ID fails at `labeler.id` before train execution.
- Error path: scalar `labeler: demo.fixlb` fails because the confirmed authored shape is an ID-only mapping.
- Integration: resolving a `TrainLaneConfig` dataclass still round-trips through validation and does not preserve any `source` field for labeler selection.

**Verification:**
- Train configs can no longer express label source kinds or label params.
- Strategy and labeler top-level selections are mutually exclusive.
- Resolved train config evidence contains top-level labeler ID, not nested `train.label.source`.

### U2. Update Train Execution and Labeler Evidence

**Goal:** Make train execution consume the new labeler config shape while preserving fixed component execution, data-array preflight, and reviewer-readable label component evidence.

**Requirements:** R2, R3, R4, R7, R10; covers F1, F2, AE3, AE5.

**Dependencies:** U1.

**Files:**
- Modify: `research/aegis_research/cli_commands/run.py`
- Modify: `research/aegis_research/experiments.py`
- Test: `tests/integration/research/aegis_research/test_train_cli.py`
- Test: `tests/integration/research/aegis_research/test_cli.py`
- Test: `tests/e2e/research/aegis_research/test_experiment_provenance.py`

**Approach:**
- Update train CLI label-result building to resolve the selected labeler component ID from the new config object.
- Preserve the component-only runtime behavior: the selected label component callable still owns generator params and returns a native-first label result.
- Enrich label metadata or adjacent train evidence with selected component identity sufficient for reviewers: component ID, version, repo-relative source path, and source hash.
- Remove `config.label.source` branching in data-array preflight; train labeler input arrays are always read from the selected label component.
- Update any missing-label-builder or train-mode diagnostic language that still refers to component label source refs.

**Execution note:** Add or update train CLI integration coverage before changing artifact metadata so source identity regressions are visible.

**Patterns to follow:**
- Existing `_label_result_builder` component loading in `research/aegis_research/cli_commands/run.py`.
- Component source identity shape from `research/aegis_research/component_registry/contracts.py`.
- Data-array preflight pattern in `research/aegis_research/experiments.py`.
- Thin train wrapper behavior in `research/aegis_research/training.py`, which should remain unchanged unless implementation discovers a direct dependency on the old label shape.

**Test scenarios:**
- Happy path, covers AE5: `aerd run --train` with top-level labeler ID executes the label component and records completed ML-training evidence.
- Integration: label component input arrays still participate in train data-array preflight after `config.label.source` is removed.
- Integration: selected labeler evidence includes stable component identity, not just authored config ID.
- Error path: unknown labeler ID fails before label component execution and before training artifacts imply stale playbook state.
- Error path: a failing label component records train failure evidence that points to the selected component, not a label playbook or playground.
- Regression: shared train-config helpers used by CLI integration tests emit top-level `labeler: {id: ...}` while leaving model settings under the train block.
- Regression: lower-level `LabelConfig` and `build_label_result` usage inside `docs/examples/components/label_component_example.py` remains valid component-internal behavior.

**Verification:**
- Train execution no longer reads a label source discriminator from config.
- Labeler evidence is enough for a reviewer to trace the fixed component source used by a train run.
- Label component params remain source-owned and do not enter train YAML.

### U3. Narrow Active Playbook Families

**Goal:** Remove labels from active playbook family/stage declarations while preserving indicator and strategy playbook discovery, validation, and execution.

**Requirements:** R1, R5, R8, R9; covers F3, AE2, AE4.

**Dependencies:** None.

**Files:**
- Modify: `research/aegis_research/playbook_registry/contracts.py`
- Modify: `research/aegis_research/playbook_registry/registry.py`
- Modify: `research/aegis_research/playbook_registry/__init__.py`
- Modify: `research/playbooks/labels/README.md`
- Test: `tests/unit/research/aegis_research/test_playbooks.py`
- Test: `tests/integration/research/aegis_research/test_run_playbook_sources.py`

**Approach:**
- Narrow active playbook families and stages to indicators and strategies only.
- Let the existing registry iteration naturally discover only active playbook families, while documenting the label playbook directory as a non-authoring tombstone or removing active authoring language.
- Keep component registry label support unchanged; labels remain a component family, not a playbook family.
- Preserve existing indicator playbook metadata such as indicator family and baseline component indicator ID.
- Preserve existing strategy playbook behavior, candidate grid validation, and central portfolio scoring paths.

**Patterns to follow:**
- Existing `PLAYBOOK_FAMILIES` and `PLAYBOOK_STAGES` central constants.
- Existing unit tests for unsupported stage and duplicate playbook IDs.
- Run playbook integration tests in `tests/integration/research/aegis_research/test_run_playbook_sources.py`.

**Test scenarios:**
- Happy path, covers AE4: indicator playbooks still discover by stable ID and load callable behavior.
- Happy path, covers AE4: strategy playbooks still execute through the run-lane playbook source tests.
- Error path, covers AE2: a playbook manifest declaring label family or label stage is rejected as unsupported when encountered through active registry validation.
- Regression: `PLAYBOOK_FAMILIES` public export no longer lists labels, while component families still include labels.
- Regression: run configs using `strategy.source: playbook` and `indicators[].source: playbook` continue to validate and run.

**Verification:**
- Active playbook registry surfaces only indicator and strategy families.
- Label component discovery remains available.
- Existing composed strategy candidate tests are unaffected by label family removal.

### U4. Update Fixtures, Docs, and Public Examples

**Goal:** Align committed configs, public docs, and docs tests with top-level component-only labelers while preserving explicit source refs for strategy and indicator run sources.

**Requirements:** R2, R3, R4, R8, R9, R11; covers F1, F2, F3, AE1, AE3, AE4, AE6.

**Dependencies:** U1, U3.

**Files:**
- Modify: `docs/components.md`
- Modify: `docs/playbooks.md`
- Modify: `docs/vectorbt-scaffold.md`
- Modify: `README.md`
- Modify: `tests/support/research/aegis_research/fixtures/experiments/synthetic_ml_scaffold_fixture.yaml`
- Modify: `tests/support/research/aegis_research/fixtures/experiments/synthetic_purged_fixlb_scaffold_fixture.yaml`
- Modify: `tests/integration/research/aegis_research/test_cli_docs.py`

**Approach:**
- Update train YAML examples and fixtures to use top-level `labeler: {id: ...}` and remove nested `train.label` examples.
- Keep `model` under the train block with `source: plugin`; this plan does not redesign model refs.
- Update docs to state that labels are fixed reviewed components and that labeler params live inside percent-cell component source.
- Update playbook docs to describe only indicator and strategy playbooks as active playbook families.
- Keep run-lane examples explicit about `source: component` and `source: playbook` for strategy and indicator refs.
- Avoid editing historical `docs/solutions/` content unless active docs tests consume it.

**Patterns to follow:**
- Current docs style in `docs/components.md`, `docs/playbooks.md`, and `docs/vectorbt-scaffold.md`.
- Existing docs assertions in `tests/integration/research/aegis_research/test_cli_docs.py`.
- Label component example pattern in `docs/examples/components/label_component_example.py`.

**Test scenarios:**
- Happy path, covers AE1: train fixture YAML with top-level labeler ID mapping is accepted by config loading tests.
- Docs regression, covers AE4: active docs show labelers as component-only and do not describe label playbooks as active.
- Docs regression: active docs still show `source: component` and `source: playbook` for strategy/indicator run sources.
- Docs regression: active docs explain that labeler params are edited inside reviewed component source, not run YAML.
- Docs regression, covers AE6: docs state `strategy` and `labeler` are mutually exclusive top-level selections.

**Verification:**
- Active docs and fixtures present one consistent train labeler shape.
- Docs tests distinguish labeler component-only config from run source refs instead of requiring source refs everywhere.
- No active docs suggest label playbook, label playground, or label sweep authoring.

---

## System-Wide Impact

- **Interaction graph:** Config validation, config dataclasses, train execution, train artifact metadata, playbook discovery, public docs, fixtures, and docs tests are affected. Indicator/strategy run execution should remain behaviorally unchanged.
- **Error propagation:** Static config shape errors should remain `config_validation` failures before train execution and before run directories are created where the existing CLI contract already avoids side effects.
- **State lifecycle risks:** Removing nested `train.label` changes authored/resolved config evidence; reviewers should use selected labeler component evidence for source traceability.
- **API surface parity:** `aerd run` keeps top-level `strategy`; `aerd run --train` gains top-level `labeler`. Model refs still keep `source: plugin` because this plan is labeler-specific.
- **Integration coverage:** Unit tests alone cannot prove train CLI artifact evidence or playbook preservation, so integration coverage must include train CLI and run playbook paths.
- **Unchanged invariants:** Component registry labels remain valid; label helper internals remain available to components; indicator and strategy playbooks remain valid sweep mechanisms; configs still reject inline code, paths, formulas, and stale run artifact refs.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Old train fixtures or docs keep nested `train.label` and make the contract inconsistent. | Update fixtures and active docs in the same change as the schema/validator update; add docs tests for top-level labeler shape. |
| Removing labels from playbook families accidentally breaks indicator/strategy playbooks. | Keep run-lane source-ref types unchanged and run existing playbook integration tests after narrowing family constants. |
| Labeler evidence becomes weaker after `source` is removed from authored YAML. | Add selected component identity to runtime labeler evidence using component registry metadata. |
| Validator accepts both old and new shapes by accident. | Add explicit rejection tests for nested `train.label`, `labeler.source`, and `labeler.params`; avoid compatibility shims. |
| Schema-version expectations are unclear for existing local configs. | Treat this as an in-flight forward-first schema cleanup and keep field-level validation actionable; revisit version bump only if implementation finds an established repo policy requiring it. |

---

## Documentation / Operational Notes

- Active docs should show `labeler` as the train counterpart to `strategy`, not as another source-ref family.
- Public component docs should continue to explain percent-cell label component authoring and that params live in source.
- Playbook docs should explicitly limit active playbooks to indicators and strategies.
- Fixture configs under `tests/support/research/aegis_research/fixtures/experiments/` should be treated as canonical examples and updated with the config change.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-20-label-component-only-contract-requirements.md](../brainstorms/2026-05-20-label-component-only-contract-requirements.md)
- Related requirements: `docs/brainstorms/2026-05-17-vectorbt-label-contract-requirements.md`
- Related workflow requirements: `docs/brainstorms/2026-05-18-research-playbook-component-workflow-requirements.md`
- Related batched playbook requirements: `docs/brainstorms/2026-05-20-vbt-native-batched-playbook-contract-requirements.md`
- Related learning: `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`
- Related learning: `docs/solutions/logic-errors/vectorbt-label-contract-target-lineage-2026-05-17.md`
- Related learning: `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md`

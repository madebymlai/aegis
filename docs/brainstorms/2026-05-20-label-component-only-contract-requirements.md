---
date: 2026-05-20
topic: label-component-only-contract
---

# Label Component Only Contract

## Summary

Remove label playbook, playground, and sweep semantics from the active research contract. Configs should select either a top-level strategy or a top-level labeler, never both; labelers are selected by stable component ID only, with params fixed inside reviewed Jupytext-compatible component source.

---

## Problem Frame

The current scaffold has already moved toward fixed reviewed label components for train mode, but older playbook/playground language and registry shape still make labels look like they might share the exploratory sweep surface used by indicators and strategies. That ambiguity is expensive because label generation carries look-ahead semantics, target transforms, and split-safety assumptions that should be reviewed as a fixed training contract, not tuned ad hoc from run YAML or stale playground code.

The drift also creates a maintenance trap. Indicator and strategy playbooks remain useful because their sweep candidates feed centrally scored strategy research, but labeler sweeps belong to an older flow that is deprecated and not working. Leaving that path visible invites planners or agents to preserve dead surface area, add compatibility shims, or design around a source discriminator that no longer represents a real choice.

---

## Actors

- A1. Config author: Selects either a strategy source for `aerd run` or a labeler component for `aerd run --train`.
- A2. Label component author: Encodes fixed label generator params, target transform, and split-safety metadata in reviewed component source.
- A3. Training runner: Resolves the configured label component and executes it under the train contract.
- A4. Reviewer or automation agent: Audits configs, docs, and artifacts without guessing whether label playbooks are still supported.

---

## Key Flows

- F1. Select a training label
  - **Trigger:** A config author writes or reviews a train-mode config.
  - **Actors:** A1, A3, A4
  - **Steps:** The config names one stable top-level labeler component ID. The runner resolves that ID from reviewed label components, treats the component source kind as implied, and rejects attempts to combine labeler/train selection with strategy/run selection, select label playbooks, label playgrounds, label sweeps, or config-supplied label params.
  - **Outcome:** The training label boundary is unambiguous and does not expose a fake source choice.
  - **Covered by:** R1, R2, R5, R6, R11
- F2. Author a fixed label component
  - **Trigger:** A researcher wants to adjust label generator params or target-transform behavior.
  - **Actors:** A2, A4
  - **Steps:** The author edits or creates a reviewed label component file, keeps params and target decisions in the component source, and relies on component metadata and callable behavior for reviewable reproducibility.
  - **Outcome:** Label behavior changes through source review rather than config-time sweep knobs.
  - **Covered by:** R3, R4, R7
- F3. Clean up stale labeler surface
  - **Trigger:** A planner or implementer removes deprecated label playground behavior.
  - **Actors:** A3, A4
  - **Steps:** User-facing docs, examples, validation, and active discovery surfaces stop presenting labels as playbook-backed or sweepable while preserving indicator and strategy playbook semantics.
  - **Outcome:** Agents and reviewers no longer encounter contradictory labeler paths.
  - **Covered by:** R1, R5, R8, R9

---

## Requirements

**Label source boundary**
- R1. Training labels must be an active component-only contract; label playbooks, label playgrounds, and label sweeps must not remain supported executable train-label sources.
- R2. Train-mode labeler selection must live at the top level as an ID-only mapping; the component source kind is implied and should not be authored as a label source discriminator.
- R3. Label generator params, target selection, target transforms, output declarations, and split-safety assumptions must be fixed in reviewed label component source rather than supplied by train YAML.
- R4. Label component source must remain reviewable and manually configurable through the existing Python percent-cell component style.

**Validation and failure behavior**
- R5. Config validation must fail fast when a train config attempts to use a label playbook, label playground path, label sweep axis, inline label code, or label params outside the selected component.
- R6. Removing `source` from label selection must be treated as a forward contract cleanup, not as a compatibility layer that silently accepts multiple old label shapes.
- R7. The existing native label-building behavior may remain available to label components, but it must not expose label sweep authoring as a public train-config surface.

**Docs, examples, and consistency**
- R8. Public docs and examples must describe labels as fixed reviewed components for train mode and avoid suggesting that labels participate in the playbook sweep lane.
- R9. Indicator and strategy playbooks must remain explicitly allowed for research sweeps; this cleanup is label-specific and must not weaken composed indicator/strategy candidate semantics.
- R10. Run and train artifacts must remain understandable to reviewers: label evidence should point back to the fixed selected component, not to hidden config params or stale playground state.
- R11. Configs must keep top-level labeler/train selection and top-level strategy/run selection mutually exclusive: if a strategy source is present, labeler selection must be absent; if a labeler is present, strategy selection must be absent.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R5.** Given a train config that names a known top-level labeler mapping with only an `id`, when validation runs, the config is accepted without requiring a label source field.
- AE2. **Covers R1, R5, R6.** Given a train config that tries to select a label playbook or playground path, when validation runs, it fails before train execution rather than routing through a legacy labeler path.
- AE3. **Covers R3, R4, R7.** Given a researcher wants a different `FIXLB` horizon or target threshold, when they change label behavior, the change is made in reviewed label component source rather than as config params or a sweep axis.
- AE4. **Covers R8, R9.** Given a reader compares label docs with indicator and strategy playbook docs, when they inspect supported source modes, labels are clearly component-only while indicator and strategy playbooks remain available for sweeps.
- AE5. **Covers R10.** Given a completed train run, when a reviewer inspects label evidence, the selected label component identity is sufficient to trace the fixed label behavior without reconstructing hidden labeler playground state.
- AE6. **Covers R11.** Given a config that includes both a strategy source and labeler selection, when validation runs for either lane, it fails before execution instead of guessing whether the author intended a strategy run or train run.

---

## Success Criteria

- Config authors have one obvious way to select training labels: choose the reviewed top-level labeler component ID.
- Label component authors can still manually configure params in Python percent-cell source, preserving the current reviewable workflow.
- Reviewers and agents no longer see label playbooks, label playgrounds, or label sweeps as active choices.
- Downstream planning does not need to invent whether label source kinds, label config params, or label sweeps should be preserved.
- Config authors cannot accidentally mix strategy-run and labeler-train concerns in one active config.
- Indicator and strategy sweep workflows continue to read as intentionally separate from the fixed label training contract.

---

## Scope Boundaries

- No replacement labeler playground or UI.
- No train-config label params, formulas, inline Python, notebook paths, arbitrary script paths, or sweep axes.
- No automatic generation or promotion of label components.
- No compatibility shim for old label playbook or playground config shapes unless a concrete external consumer is identified later.
- No changes to indicator or strategy playbook sweep semantics beyond removing label-related confusion.
- No expansion of model families, target kinds, or split-validation support as part of this cleanup.

---

## Key Decisions

- Component-only labels: Labels are reviewed training components, not exploratory playbook sweep candidates.
- Top-level ID-only labeler config: The label source discriminator should disappear because there is no longer a supported source choice for train labelers, and labeler selection should sit beside `strategy` as the train-lane counterpart using an ID-only mapping.
- Params live with source: Label params belong in the component file so review captures target meaning, look-ahead assumptions, and split-safety implications together.
- Forward-first cleanup: Removing stale labeler paths is preferred over preserving deprecated behavior that does not work.
- Label-specific change: Indicator and strategy playbooks remain the right mechanism for research sweeps and composed strategy candidates.

---

## Dependencies / Assumptions

- `docs/vectorbt-scaffold.md` already states that train-mode labels use fixed label components rather than label playbooks.
- `docs/components.md` already states that component callables own fixed reviewed defaults and that lane configs do not pass per-run params into component code.
- `docs/playbooks.md` still describes playbook registry families that include labels, so planning should align that surface with the component-only label decision.
- `docs/examples/components/label_component_example.py` is the current public example for a reviewed label component.
- Current repo scan found no committed label playbook files under `research/playbooks/labels/`.
- `research/aegis_research/playbook_registry/contracts.py` still includes `labels` in the playbook family type, which is stale relative to this requirement.
- `research/aegis_research/configuration/schema.py` currently models train label selection under the train block with a generic source ref, which is broader than the desired top-level ID-only labeler contract.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R2, R5, R6, R11][Technical] What exact typed config object and validation path should represent the new top-level ID-only labeler mapping?
- [Affects R1, R8, R9][Technical] Which playbook registry docs, tests, and type declarations should be narrowed so labels no longer appear as a runnable playbook family?
- [Affects R8][Technical] Which public examples or scaffold docs still mention label playbooks, label playgrounds, or label sweeps and need cleanup?

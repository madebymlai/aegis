---
date: 2026-05-21
topic: single-run-path-train-lane-removal
---

# Single Run Path Train-Lane Removal

## Summary

Remove the train lane as an active product and code path so Aegis has one canonical execution path: `aerd run`. Delete `--train`, model-plugin training, train labels, train/run mode semantics, and active user-facing language that implies multiple execution lanes remain.

---

## Problem Frame

Aegis has converged on strategy and research evidence as the primary workflow, while the supervised label/model training path now creates more carrying cost than value. The split between `run` and `train` forces config validation, CLI behavior, docs, tests, artifacts, and review language to preserve a second mental model that the project no longer wants to support.

Keeping train-lane language also makes new run-path work harder to reason about. Reviewers and agents can infer that run-lane features must coexist with label/model training semantics, even when the intended direction is a single path centered on candidate generation, portfolio simulation, metrics, and run evidence.

---

## Actors

- A1. Research user: Runs strategy or component/playbook research and needs one obvious command path.
- A2. Planning or implementation agent: Needs an unambiguous cleanup contract to remove legacy train surfaces without preserving accidental compatibility.
- A3. Aegis run path: Loads run configs, executes strategy/research evidence, writes artifacts, and reports results.

---

## Key Flows

- F1. Single canonical run execution
  - **Trigger:** A research user runs a supported config.
  - **Actors:** A1, A3
  - **Steps:** The user calls `aerd run`; Aegis validates the config as a single supported run path, executes strategy/research evidence, and writes run artifacts without checking for a train mode or alternate training command.
  - **Outcome:** The command and artifacts represent one canonical execution path, not one lane among several.
  - **Covered by:** R1, R2, R3, R4

- F2. Legacy train-shaped config rejection
  - **Trigger:** A stale config still contains train, labeler, model, or training-only fields.
  - **Actors:** A1, A3
  - **Steps:** Aegis validates the config before execution, rejects unsupported training-only fields, and does not route the user toward `--train` or another ML training path.
  - **Outcome:** Obsolete train configs fail fast as unsupported inputs rather than being preserved through compatibility behavior.
  - **Covered by:** R5, R6, R7

- F3. Documentation and example cleanup
  - **Trigger:** A user, reviewer, or agent reads active docs, examples, or tests to understand how Aegis runs research.
  - **Actors:** A1, A2
  - **Steps:** Active material describes the single run path, avoids train-vs-run lane framing, and omits model-plugin and train-label examples as supported workflows.
  - **Outcome:** Readers do not infer that model training or train labels are part of the current supported product surface.
  - **Covered by:** R8, R9, R10

---

## Requirements

**Single execution path**
- R1. `aerd run` must be the only supported command path for executing Aegis research configs.
- R2. The `--train` flag must be removed from the active CLI contract.
- R3. Active command output, structured results, and user-facing docs must not describe `run` as one mode or lane among multiple active execution paths.
- R4. Existing strategy/research run behavior must remain the supported path after the cleanup.

**Train-lane removal**
- R5. Model-plugin training must be removed as an active capability, including the registry, built-in plugin path, training orchestration, prediction-to-signal model validation flow, and model export surfaces that only serve train output.
- R6. Train labels must be removed as an active capability, including labeler config semantics, train label components, label target artifacts, and label/model compatibility behavior that only exists for supervised training.
- R7. Train-only config fields and stale train-shaped configs must fail fast as unsupported inputs, without compatibility shims or guidance to use another active training command.

**Language and docs**
- R8. Active docs and examples must describe one supported run path and must remove train-mode, model-plugin, train-label, and train-vs-run guidance.
- R9. Active code and tests should prefer single-path naming where practical; retain `run` as the user-facing path without adding new labels that imply competing modes.
- R10. Historical brainstorms, plans, and solution notes may remain as historical records, but they must not be updated to imply train support is still active.

**Forward-first cleanup**
- R11. The cleanup must not introduce backward-compatibility shims, migration adapters, or legacy fallback execution for removed train configs.
- R12. Shared utilities should survive only when they are still required by the single run path; otherwise they should be deleted rather than preserved for hypothetical future training work.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R4.** Given a valid strategy/research config, when a user runs `aerd run`, Aegis executes the supported run path and the result does not include mode or lane evidence for an alternate train path.
- AE2. **Covers R2, R7, R11.** Given a user passes `--train`, when CLI parsing or command validation runs, the flag is not accepted as an active command option and Aegis does not route to ML training.
- AE3. **Covers R5, R6, R7.** Given a stale config containing train/model/labeler fields, when config validation runs, Aegis rejects it as unsupported training configuration before execution and does not suggest an alternate training command.
- AE4. **Covers R8, R9.** Given a reader opens active docs or examples, when they search for current execution guidance, they find `aerd run` as the supported command and do not find model-plugin training or train labels presented as active workflows.
- AE5. **Covers R10.** Given a historical brainstorm or plan references train-lane removal context, when the cleanup lands, those documents may remain as historical records without being treated as current product guidance.

---

## Success Criteria

- Research users have one obvious supported command path for Aegis research execution.
- Agents and reviewers no longer need to preserve model-plugin training, train labels, or train/run mode compatibility while planning run-path work.
- Active docs, examples, and tests no longer describe `--train`, model plugins, or train labels as supported features.
- The codebase has less validation, registry, artifact, and execution surface dedicated only to the removed train path.

---

## Scope Boundaries

- Do not add a replacement supervised ML training workflow.
- Do not migrate old train configs or preserve them through compatibility behavior.
- Do not expand rolling OOS implementation while performing this cleanup; keep this work focused on deleting train-path carrying cost and preserving the existing supported run path.
- Do not redesign live trading, NautilusTrader execution, RL, contextual bandits, or allocation policy learning as part of this cleanup.
- Do not rewrite historical brainstorms, plans, or solution documents beyond avoiding current-doc confusion.
- Do not delete run-path strategy, indicator, candidate, portfolio, metric, leaderboard, manifest, or provenance behavior that remains part of supported `aerd run` research execution.

---

## Key Decisions

- Single path over dual-mode cleanup: Keep `aerd run` as the product path and remove train-vs-run framing rather than preserving `run` as one lane beside a deleted lane.
- Delete train labels with train execution: Labeler config and label target artifacts are part of the removed train path, not a separate capability to preserve by default.
- Forward-first removal: Stale train inputs should fail as unsupported rather than route through warnings, migrations, or compatibility shims.
- Preserve historical records: Existing dated brainstorms and plans can still mention train-lane history, but active docs and examples must reflect the current supported surface.

---

## Dependencies / Assumptions

- Current strategy/research `aerd run` behavior is the supported path to preserve.
- No external consumer currently depends on train-mode execution as a supported public interface.
- Any shared utility that appears train-related must be checked against the run path before deletion.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R5, R6, R12][Technical] Which train-adjacent modules are exclusively training support versus still used by the single run path?
- [Affects R8, R10][Technical] Which docs and examples are active guidance versus historical records that should remain untouched?
- [Affects R9, R12][Technical] Which internal names should be renamed now for single-path clarity versus left temporarily to avoid unnecessary churn?

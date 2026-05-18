---
date: 2026-05-18
topic: baseline-experiment-examples
github_issue: 13
---

# Baseline Experiment Examples

## Summary

Issue #13 will move the current synthetic baseline YAMLs into test-only fixture territory, replace the public experiment-config shelf with a README pointer, and create a runnable notebook walkthrough for humans. The notebook should use an inline config and explicit model registry so it teaches the scaffold without shipping a public "baseline strategy" YAML.

---

## Problem Frame

`research/configs/experiments/` currently contains synthetic baseline YAMLs that are useful deterministic scaffolds for regression coverage. Their location and naming also make them easy to read as recommended experiment baselines, even though they use synthetic data, a test model plugin id, uncalibrated positive-class probabilities, fixed scaffold thresholds, and many explicit research assumptions.

Issue #13 is about preventing that mismatch. The project still needs deterministic configs for tests and examples of how the research loop works, but public-facing docs should not imply that a checked-in YAML file is methodology evidence or a trading recommendation.

---

## Actors

- A1. Test suite: Loads deterministic experiment fixtures to verify config, validation, portfolio, provenance, and report behavior.
- A2. New reader or researcher: Looks for a safe way to learn how to run and reason about the scaffold.
- A3. Documentation maintainer: Keeps public examples aligned with the current config, model-plugin, signal, portfolio, and report contracts.
- A4. Future planning or implementation agent: Needs clear scope boundaries so fixture movement, docs, and notebook behavior do not drift into methodology work.

---

## Key Flows

- F1. Test fixture use
  - **Trigger:** Automated tests need deterministic experiment configs.
  - **Actors:** A1, A4
  - **Steps:** Load the moved synthetic configs from a test-only fixture location, run the same regression scenarios that currently depend on the baseline YAMLs, and preserve their role as scaffold coverage.
  - **Outcome:** Regression coverage remains stable without presenting those YAMLs as public experiment examples.
  - **Covered by:** R1, R2, R3, R12
- F2. Human discovery from experiment configs
  - **Trigger:** A reader opens `research/configs/experiments/` looking for examples.
  - **Actors:** A2, A3
  - **Steps:** Read a short README that explains why runnable baseline YAMLs are not stored there and points to the notebook walkthrough.
  - **Outcome:** The directory no longer invites users to run or copy synthetic baseline configs as strategy templates.
  - **Covered by:** R4, R5, R6, R10
- F3. Notebook walkthrough
  - **Trigger:** A reader wants a runnable, educational example.
  - **Actors:** A2, A3
  - **Steps:** Open the notebook, inspect an inline example config, register the example model plugin explicitly, run a small synthetic scaffold experiment, and read the caveats around synthetic evidence and methodology limits.
  - **Outcome:** The reader learns the research loop and artifact shape without mistaking the example for empirical edge.
  - **Covered by:** R7, R8, R9, R10, R11

---

## Requirements

**Fixture separation**
- R1. The existing synthetic baseline YAMLs must be moved out of `research/configs/experiments/` into a test-only fixture context.
- R2. The moved YAMLs must keep serving deterministic regression coverage for the same scaffold behaviors they currently exercise.
- R3. Test-facing fixture names or surrounding docs must make their role clear as scaffold fixtures, not methodology baselines or research candidates.

**Experiment config directory**
- R4. `research/configs/experiments/` must not contain the synthetic baseline YAMLs after this change.
- R5. `research/configs/experiments/` must contain a README or equivalent pointer explaining that public runnable baseline YAMLs are intentionally absent.
- R6. The README must direct readers to the notebook walkthrough as the human-facing way to learn the experiment flow.

**Notebook walkthrough**
- R7. A new notebook walkthrough must be added under the docs examples area rather than under the experiment config directory.
- R8. The notebook must use an inline example config instead of loading or creating a docs-owned baseline YAML file.
- R9. The notebook must register the example model plugin explicitly before resolving or running the experiment, so it does not depend on hidden CLI registry behavior.
- R10. The notebook and README must state that the example is scaffold evidence only and not a validated trading methodology, empirical edge claim, or investment recommendation.
- R11. The notebook must explain the major assumptions that make the example educational rather than evidentiary: synthetic data, fixed label/target shape, test/example model plugin, uncalibrated probabilities, fixed signal thresholds, execution assumptions, portfolio sizing, and report gates.

**Reference cleanup**
- R12. Existing tests and docs that reference the old `research/configs/experiments/` baseline YAML paths must be updated to the new fixture and notebook roles.
- R13. Public docs must avoid commands that tell readers to run the old synthetic baseline YAMLs from `research/configs/experiments/`.
- R14. Historical plans and brainstorm docs do not need retroactive edits unless they are actively used as current user-facing instructions.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R12.** Given the current synthetic baseline YAMLs are moved, when the existing regression tests are updated, they load the configs from a test-only fixture context and still verify deterministic scaffold behavior.
- AE2. **Covers R4, R5, R6, R13.** Given a reader opens `research/configs/experiments/`, when they look for runnable examples, they see a README pointer to the notebook rather than baseline YAML files or commands that imply a strategy baseline.
- AE3. **Covers R7, R8, R9.** Given the reader opens the notebook walkthrough, when they run it, the notebook defines or embeds the example config inline and registers the model plugin explicitly before running the experiment.
- AE4. **Covers R10, R11.** Given the notebook completes a synthetic run, when the reader reviews the narrative, it frames the output as scaffold evidence and names the key assumptions that prevent it from being methodology evidence.
- AE5. **Covers R14.** Given older planning documents mention the original baseline paths historically, when issue #13 is implemented, those archived references may remain unless they are presented as current instructions.

---

## Success Criteria

- A new reader no longer sees `research/configs/experiments/` as a shelf of recommended baseline strategies.
- The project keeps deterministic experiment coverage without conflating test fixtures with public research examples.
- The notebook gives humans a runnable, explicit-registry path to understand the scaffold and its artifacts.
- Planning can proceed without inventing whether to move the YAMLs, whether to add a notebook, whether the notebook should be runnable, or whether methodology metadata belongs in this pass.

---

## Scope Boundaries

- Do not add methodology metadata to the experiment config schema in issue #13.
- Do not add provider-backed public configs, proprietary symbols, credentialed examples, or empirical performance claims.
- Do not turn the synthetic example into a research candidate, strategy template, or trading recommendation.
- Do not fix the CLI model-registry path as part of this issue; the notebook should use explicit registry setup.
- Do not create a second docs-owned YAML baseline file for the notebook.
- Do not retroactively rewrite archived plans and brainstorms unless they function as current user-facing instructions.

---

## Key Decisions

- Test-only fixtures over public baseline YAMLs: deterministic configs remain valuable for regression coverage, but their current public location overstates their methodology meaning.
- Runnable notebook over static docs: readers still need a hands-on example, but the explanation and caveats belong in a guided document rather than a bare YAML file.
- Inline notebook config over docs YAML: the notebook can teach the config shape without creating another file that may drift into an implied baseline.
- README pointer in `research/configs/experiments/`: the empty-or-nearly-empty directory should actively redirect readers rather than looking accidentally unfinished.

---

## Dependencies / Assumptions

- The report-metrics/survival-gate work from `docs/plans/2026-05-18-002-feat-report-metrics-survival-gates-plan.md` is treated as completed prerequisite context for issue #13.
- Current tracked synthetic configs are `research/configs/experiments/synthetic_ml_baseline.yaml` and `research/configs/experiments/synthetic_purged_fixlb_baseline.yaml`.
- `docs/examples/` already exists and includes model-plugin notebook material, making it the natural home for the new walkthrough.
- The CLI currently uses an empty model registry, so notebook runnability should come from explicit registry setup rather than CLI defaults.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R12][Technical] What exact test fixture path should hold the moved synthetic YAMLs?
- [Affects R7][Technical] What exact notebook path and title should fit the existing `docs/examples/` organization?
- [Affects R12, R13][Technical] Which current docs are active user-facing instructions and therefore require updates, versus archived planning context that can remain historical?

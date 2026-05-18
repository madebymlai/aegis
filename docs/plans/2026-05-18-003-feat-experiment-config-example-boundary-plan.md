---
title: feat: Separate Experiment Fixtures From Public Examples
type: feat
status: active
date: 2026-05-18
origin: docs/brainstorms/2026-05-18-baseline-experiment-examples-requirements.md
---

# feat: Separate Experiment Fixtures From Public Examples

## Summary

Move the synthetic experiment configs into test-only fixtures, make `research/configs/experiments/` tracked README-only through `.gitignore`, and add a runnable scaffold notebook that uses inline config plus explicit model registry setup. Active docs and tests should point to fixtures or the notebook by role, not to public synthetic baseline YAMLs.

---

## Problem Frame

The origin requirements identify a perception bug: deterministic scaffold YAMLs are useful for regression coverage, but their public experiment-config location makes them look like recommended strategy baselines. Planning also resolved that future files under `research/configs/experiments/` should stay local by default, with only the README tracked.

---

## Requirements

- R1. Move the existing synthetic baseline YAMLs out of `research/configs/experiments/` into a test-only fixture context. Origin: R1, R2, R3, F1, AE1.
- R2. Preserve deterministic regression coverage for the moved synthetic fixture configs. Origin: R2, F1, AE1.
- R3. Rename or document fixture identity so test-facing assets are scaffold fixtures, not methodology baselines. Origin: R3, success criteria.
- R4. Make `research/configs/experiments/` tracked README-only for future files, while preserving local untracked experiment configs. Origin: R4, R5, user planning decision.
- R5. Add a generic README pointer in `research/configs/experiments/` that directs readers to the notebook walkthrough. Origin: R5, R6, F2, AE2; user planning decision.
- R6. Add a runnable notebook walkthrough under `docs/examples/` that uses inline config and explicit model registry setup. Origin: R7, R8, R9, F3, AE3.
- R7. Notebook and docs must frame scaffold outputs as educational scaffold evidence only, not validated trading methodology, empirical edge, or investment advice. Origin: R10, R11, AE4.
- R8. Update active tests, docs, and notebooks that reference the old synthetic config paths. Origin: R12, R13, AE1, AE2, AE5.
- R9. Do not add config schema methodology metadata, provider-backed examples, or a CLI model-registry fix in this issue. Origin: Scope Boundaries.

**Origin actors:** A1 test suite, A2 new reader or researcher, A3 documentation maintainer, A4 future planning or implementation agent.

**Origin flows:** F1 test fixture use, F2 human discovery from experiment configs, F3 notebook walkthrough.

**Origin acceptance examples:** AE1 fixture regression coverage, AE2 experiment directory README pointer, AE3 inline-config explicit-registry notebook, AE4 scaffold-only caveats, AE5 archived references may remain historical.

---

## Scope Boundaries

- Do not add methodology metadata to the experiment config schema.
- Do not add provider-backed public examples, proprietary symbols, credentialed examples, or empirical performance claims.
- Do not turn the synthetic example into a research candidate, strategy template, or trading recommendation.
- Do not fix the CLI model-registry path; docs should route synthetic walkthroughs through explicit-registry notebook/Python flow.
- Do not create a second docs-owned YAML baseline file for the notebook.
- Do not retroactively rewrite archived plans and brainstorms unless they function as current user-facing instructions.
- Do not add special explanatory text about the existing provider-backed ETF config in the generic experiment README; the directory-level README should stay a generic pointer.

### Deferred to Follow-Up Work

- Provider-backed config policy: decide separately whether local/provider experiment configs need their own private examples area, fixture story, or methodology metadata.
- CLI registry UX: resolve separately so future docs can safely include CLI-run examples with registered plugins.

---

## Context & Research

### Relevant Code and Patterns

- Current synthetic configs are `research/configs/experiments/synthetic_ml_baseline.yaml` and `research/configs/experiments/synthetic_purged_fixlb_baseline.yaml`.
- A provider-backed config currently exists at `research/configs/experiments/etf_cspx_dtla_sgln_yfinance_ml.yaml`; planning resolved to remove it from tracking while preserving it locally.
- Tests currently load old synthetic config paths in `tests/research/aegis_research/test_config_contract.py`, `tests/research/aegis_research/test_experiment_provenance.py`, `tests/research/aegis_research/test_experiments_purged.py`, `tests/research/aegis_research/test_validation_artifacts.py`, `tests/research/aegis_research/test_model_export.py`, `tests/research/aegis_research/test_run_lifecycle.py`, and `tests/research/aegis_research/test_provenance_manifest.py`.
- Existing model plugin docs test parses notebook JSON in `tests/research/aegis_research/test_model_plugin_example.py`; extend this source-level pattern for the new walkthrough and old-path absence checks.
- `docs/vectorbt-scaffold.md` currently shows a CLI command for the synthetic config; this must become a notebook pointer because CLI uses an empty model registry.
- `docs/examples/model_plugins/sklearn_logistic_plugin.ipynb` currently loads the old synthetic config path; it should be updated to keep the plugin example explicit without depending on public baseline YAML.
- `.gitignore` already uses allowlist exceptions for directories such as `runs/*` with `!runs/.gitkeep`; mirror that pattern for `research/configs/experiments/` and `README.md`.

### Institutional Learnings

- `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`: experiment configs are public contracts; do not loosen validation or add hidden fallbacks to make examples easier.
- `docs/solutions/architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md`: YAML selects registered plugin ids, while trusted model code is registered explicitly before config resolution.
- `docs/solutions/logic-errors/vectorbt-label-contract-target-lineage-2026-05-17.md`: examples must keep label/target lineage and split-safety assumptions visible rather than treating derived labels as methodology evidence.
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md`: prefer forward-first cleanup over compatibility aliases for old config paths or old signal fields.
- `docs/solutions/best-practices/nasdaq-100-backtest-universe-bias-2026-05-17.md`: notebook outputs can be misleading if readers infer methodology strength from example mechanics.

### External References

- Not used. Repo patterns and institutional learnings are sufficient for this docs/test/config-boundary change.

---

## Key Technical Decisions

- Use `tests/research/aegis_research/fixtures/experiments/` for moved synthetic configs: this is close to the tests that consume them and clearly test-owned.
- Rename moved fixture filenames and config `name` values away from `baseline`: use scaffold/fixture wording so generated run labels and manifests do not keep implying methodology status.
- Add shared fixture path constants in test support: this avoids repeated raw strings and makes future fixture movement cheap.
- Make `research/configs/experiments/` tracked README-only: `.gitignore` ignores files in that directory except `README.md`, and tracked non-README configs are removed from git tracking while local copies can remain.
- Keep the README generic: it should point readers to the notebook walkthrough and explain local configs are intentionally not tracked, without special discussion of the ETF config.
- Use `docs/examples/scaffold_experiment_walkthrough.ipynb` for the new notebook: "scaffold" matches the teaching goal better than "baseline."
- Keep notebook config inline and disposable: the notebook should resolve an inline config with an explicit registry and use a temporary or otherwise throwaway output location so repeated runs do not collide or dirty tracked files.

---

## Open Questions

### Resolved During Planning

- Should the ETF/YFinance config stay tracked? No. Remove it from tracking while preserving it locally, and ignore future non-README files under `research/configs/experiments/`.
- Should the experiment README explain the ETF config? No. Keep the README generic and point to the notebook walkthrough.
- Should the synthetic fixture files keep "baseline" names? No. Rename toward scaffold/fixture wording.

### Deferred to Implementation

- Exact notebook prose and cell order: choose the smallest readable walkthrough that remains runnable and clear.
- Exact fixture constant names: pick names that fit test helper conventions once the implementation touches the test files.

---

## Output Structure

```text
research/configs/experiments/
  README.md

tests/research/aegis_research/
  experiment_config_fixtures.py
  fixtures/experiments/
    synthetic_ml_scaffold_fixture.yaml
    synthetic_purged_fixlb_scaffold_fixture.yaml

docs/examples/
  scaffold_experiment_walkthrough.ipynb
```

---

## Implementation Units

### U1. Move Synthetic Configs To Test Fixtures

**Goal:** Move the two synthetic configs into a test-owned fixture directory and rename them away from baseline terminology.

**Requirements:** R1, R2, R3; origin F1, AE1.

**Dependencies:** None.

**Files:**
- Move: `research/configs/experiments/synthetic_ml_baseline.yaml` to `tests/research/aegis_research/fixtures/experiments/synthetic_ml_scaffold_fixture.yaml`
- Move: `research/configs/experiments/synthetic_purged_fixlb_baseline.yaml` to `tests/research/aegis_research/fixtures/experiments/synthetic_purged_fixlb_scaffold_fixture.yaml`
- Create: `tests/research/aegis_research/experiment_config_fixtures.py`
- Test: `tests/research/aegis_research/test_config_contract.py`

**Approach:**
- Move the YAML content without changing the experiment semantics beyond fixture identity.
- Update the authored config `name` values to scaffold/fixture names so run labels and generated evidence no longer say baseline.
- Add small test-support constants for the fixture paths and use those constants in tests rather than repeating string literals.
- Keep the configs loaded through the same `load_experiment_config(...)` and `resolve_experiment_config(...)` boundaries to preserve schema validation coverage.

**Execution note:** Characterize the current fixture-loading test first, then move paths and update the test to use the new constants.

**Patterns to follow:**
- Existing `tests/research/aegis_research/model_plugin_fixtures.py` test helper naming.
- Current config loading assertions in `tests/research/aegis_research/test_config_contract.py`.

**Test scenarios:**
- Happy path: both moved fixture configs load with schema v2 metadata and expected signal, portfolio, and report defaults.
- Happy path: fixture config names use scaffold/fixture wording and do not include `baseline`.
- Integration: fixture path constants resolve to files that exist in the test tree.

**Verification:**
- The two synthetic configs no longer exist under `research/configs/experiments/`.
- The moved fixture configs still validate through the public config loader.

---

### U2. Update Regression Tests To Use Fixture Paths

**Goal:** Preserve existing experiment, validation, provenance, export, and lifecycle coverage after the fixture move.

**Requirements:** R2, R8; origin F1, AE1.

**Dependencies:** U1.

**Files:**
- Modify: `tests/research/aegis_research/test_config_contract.py`
- Modify: `tests/research/aegis_research/test_experiment_provenance.py`
- Modify: `tests/research/aegis_research/test_experiments_purged.py`
- Modify: `tests/research/aegis_research/test_validation_artifacts.py`
- Modify: `tests/research/aegis_research/test_model_export.py`
- Modify: `tests/research/aegis_research/test_run_lifecycle.py`
- Modify: `tests/research/aegis_research/test_provenance_manifest.py`

**Approach:**
- Replace old public synthetic config paths with fixture constants from U1.
- Keep registry setup explicit in tests that run model-bearing configs.
- Check provenance tests for assumptions tied to `source_path`; update them to assert public/private evidence shape rather than old path text.

**Patterns to follow:**
- Existing `make_model_registry()` usage in experiment-running tests.
- Current `dataclasses.replace(..., output_dir=str(tmp_path))` pattern for test isolation.

**Test scenarios:**
- Happy path: `test_synthetic_baseline_experiment_runs` equivalent still completes from the moved scaffold fixture.
- Happy path: purged FIXLB fixture remains decision-grade and writes split evidence, metrics, gate outcomes, and manifest-backed artifacts.
- Error path: public evidence byte-cap and default next-open Open-price failures still fail through the same paths after fixture movement.
- Integration: run-start provenance still records config hashes and private raw config identity without depending on the old public path.

**Verification:**
- Existing tests that covered the synthetic configs continue to cover the moved fixtures.
- No active test references the old `research/configs/experiments/synthetic_*.yaml` paths.

---

### U3. Make Experiment Config Directory Tracked README-Only

**Goal:** Keep `research/configs/experiments/` as a generic pointer location in git while allowing local experiment YAMLs to exist untracked.

**Requirements:** R4, R5, R8; origin F2, AE2; user planning decision.

**Dependencies:** U1.

**Files:**
- Modify: `.gitignore`
- Create: `research/configs/experiments/README.md`
- Remove from tracking while preserving locally: `research/configs/experiments/etf_cspx_dtla_sgln_yfinance_ml.yaml`
- Test: `tests/research/aegis_research/test_model_plugin_example.py`

**Approach:**
- Add ignore rules for all files under `research/configs/experiments/` except `README.md`.
- Remove currently tracked non-README experiment configs from git tracking without requiring local deletion.
- Keep README language generic: direct readers to the scaffold notebook and explain that local experiment configs are intentionally untracked.
- Avoid special ETF/YFinance commentary per the user's planning correction.

**Patterns to follow:**
- Existing `.gitignore` allowlist pattern for ignored directories with tracked exceptions.
- Existing source-level docs tests in `tests/research/aegis_research/test_model_plugin_example.py`.

**Test scenarios:**
- Happy path: `research/configs/experiments/README.md` exists and points to the scaffold walkthrough notebook.
- Happy path: `.gitignore` contains an ignore rule for the experiment config directory and an exception for `README.md`.
- Edge case: source-level test confirms the two synthetic YAML filenames are absent from `research/configs/experiments/`.
- Integration: tracked-file review confirms non-README experiment YAMLs are not part of the committed tree after implementation.

**Verification:**
- Fresh experiment YAMLs created under `research/configs/experiments/` remain local by default.
- The only planned tracked file under `research/configs/experiments/` is `README.md`.

---

### U4. Add Runnable Scaffold Notebook Walkthrough

**Goal:** Provide the human-facing runnable example without shipping a public baseline YAML.

**Requirements:** R6, R7, R9; origin F3, AE3, AE4.

**Dependencies:** U1, U3.

**Files:**
- Create: `docs/examples/scaffold_experiment_walkthrough.ipynb`
- Modify: `docs/examples/model_plugins/sklearn_logistic_plugin.ipynb`
- Modify: `docs/examples/model_plugins/README.md`
- Test: `tests/research/aegis_research/test_model_plugin_example.py`

**Approach:**
- Build the new notebook around a compact inline config that mirrors the scaffold fixture shape without loading any YAML from `research/configs/experiments/`.
- Register the example sklearn logistic plugin explicitly before config resolution, following the model-plugin notebook pattern.
- Use disposable output handling for notebook runs so repeated execution does not collide with prior runs or dirty tracked files.
- Explain the limitations prominently: synthetic data, fixed label/target shape, example plugin, uncalibrated probabilities, fixed thresholds, execution assumptions, portfolio sizing, and report gates.
- Update the existing model-plugin notebook so it no longer loads the old synthetic baseline YAML; keep it focused on plugin registration and point to the scaffold walkthrough for full experiment context when useful.

**Execution note:** Add notebook source-contract tests before or alongside notebook edits so old path references and missing registry setup are caught mechanically.

**Patterns to follow:**
- `docs/examples/model_plugins/sklearn_logistic_plugin.ipynb` for explicit `ModelRegistry` setup.
- `tests/research/aegis_research/test_model_plugin_example.py` for notebook JSON source assertions.
- Config resolution through `resolve_experiment_config(..., model_registry=registry)`.

**Test scenarios:**
- Covers AE3. Notebook source contains inline config construction, `ModelRegistry`, and `model_registry=registry`.
- Covers AE3. Notebook source does not contain old `research/configs/experiments/synthetic_*.yaml` paths.
- Covers AE4. Notebook source contains scaffold-only, not validated methodology, and not investment recommendation caveat language.
- Happy path: a notebook-equivalent smoke test resolves an inline config with an explicit registry and runs with temporary output.
- Edge case: repeated notebook-equivalent execution does not require reusing a fixed run id or persistent tracked output path.

**Verification:**
- A reader can follow the notebook without relying on public baseline YAMLs or hidden CLI registry behavior.
- The existing plugin notebook remains a valid explicit-registration example.

---

### U5. Clean Active Documentation References

**Goal:** Remove active instructions that tell users to run or copy the old synthetic baseline YAMLs from the public experiment config directory.

**Requirements:** R5, R7, R8, R9; origin F2, F3, AE2, AE4, AE5.

**Dependencies:** U3, U4.

**Files:**
- Modify: `docs/vectorbt-scaffold.md`
- Modify as needed: `docs/model-plugins.md`
- Test: `tests/research/aegis_research/test_model_plugin_example.py`

**Approach:**
- Replace the old synthetic CLI command in `docs/vectorbt-scaffold.md` with a pointer to the scaffold notebook walkthrough.
- Avoid replacing the old command with a different CLI config command, because CLI registry support is outside this issue.
- Leave archived planning and brainstorm references historical unless they are current user-facing instructions.
- Add source-level tests that distinguish active docs/notebooks from archived docs when checking for old public synthetic paths.

**Patterns to follow:**
- Origin R14 and AE5: historical plans and brainstorms may keep old path references.
- Existing docs tests that check required phrases rather than brittle full snapshots.

**Test scenarios:**
- Covers AE2. `docs/vectorbt-scaffold.md` points readers to the scaffold walkthrough instead of the old synthetic YAML CLI command.
- Covers AE4. Active docs include scaffold-only caveat language where they introduce the notebook.
- Covers AE5. Old synthetic config path absence checks apply to active docs/notebooks/tests while allowing archived plans and brainstorm docs to remain historical.
- Error path: docs tests fail if an active doc reintroduces `research/configs/experiments/synthetic_ml_baseline.yaml` or `research/configs/experiments/synthetic_purged_fixlb_baseline.yaml`.

**Verification:**
- Active user-facing docs no longer direct readers to run moved synthetic YAML files from `research/configs/experiments/`.
- Archived plan/brainstorm references are left intact unless intentionally updated.

---

## System-Wide Impact

- **Interaction graph:** Config fixture paths affect tests, config provenance source paths, notebooks, active docs, and git tracking rules.
- **Error propagation:** Runtime config validation remains unchanged; this plan changes where configs live and how examples are discovered.
- **State lifecycle risks:** Notebook runs should use disposable output to avoid dirtying `runs/` or colliding with prior run ids.
- **API surface parity:** No config schema, CLI flag, model registry API, or experiment runtime API changes are planned.
- **Integration coverage:** Existing experiment/provenance tests prove fixture movement does not weaken scaffold regression coverage; notebook-equivalent smoke coverage proves the new human path can run.
- **Unchanged invariants:** YAML must not define model code or import paths, and model-bearing configs still require explicit trusted registry setup outside the CLI path.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Local provider config removal from tracking surprises users who had relied on it as a shared file. | README points to the notebook for tracked examples, `.gitignore` preserves local experiment configs, and provider-config policy is deferred explicitly. |
| Renaming fixture config `name` values causes test churn in run labels or manifest evidence. | Keep semantic config fields unchanged and update only assertions that intentionally depend on fixture identity. |
| Notebook source tests pass while the notebook is not actually runnable. | Add a notebook-equivalent smoke test using inline config, explicit registry, and temporary output. |
| Active docs accidentally reintroduce CLI commands that fail because the registry is empty. | Add docs source checks for old synthetic paths and route synthetic tutorial docs through the notebook. |
| README wording becomes too specific despite user correction. | Keep README generic and avoid special ETF/YFinance commentary. |

---

## Documentation / Operational Notes

- The new notebook is the public learning path for scaffold mechanics.
- `research/configs/experiments/README.md` is a pointer, not a strategy catalog.
- Local experiment YAMLs under `research/configs/experiments/` are intentionally ignored so users can keep private experiments without committing them.
- No migration path is needed for old public synthetic config paths; this is a forward-first cleanup.

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-05-18-baseline-experiment-examples-requirements.md`
- GitHub issue: #13
- Related docs: `docs/vectorbt-scaffold.md`, `docs/examples/model_plugins/sklearn_logistic_plugin.ipynb`, `docs/examples/model_plugins/README.md`, `docs/model-plugins.md`
- Related tests: `tests/research/aegis_research/test_model_plugin_example.py`, `tests/research/aegis_research/test_config_contract.py`, `tests/research/aegis_research/test_experiments_purged.py`

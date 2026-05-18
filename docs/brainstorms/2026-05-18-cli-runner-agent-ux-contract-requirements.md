---
date: 2026-05-18
topic: cli-runner-agent-ux-contract
github_issue: 12
---

# CLI Runner Agent UX Contract

## Summary

Issue #12 will introduce `aerd` as the canonical modular CLI for agent experimentation, centered on `aerd run --json` and local private experiment defaults. When no experiment config is passed, `aerd run` should use the locally configured default experiment and make that default application visible in run output and provenance.

---

## Problem Frame

The CLI is the human and agent entry point for running research experiments. Current repo state keeps that surface narrow: `research/aegis_research/cli.py` exposes a single `run` subcommand, docs still show `python -m research.aegis_research.cli ...`, and `pyproject.toml` does not define an installed console-script command.

That shape is workable for early scaffolding, but it is too weak for agents iterating on experiment configs, indicator settings, and model-training outcomes. Agents need one stable command to execute, parse, and recover from without scraping human text. They also need a way to set a local default experiment for repeated iteration without repeatedly passing the same path, while still preserving reproducibility evidence when that default affects a run.

Adjacent contracts already define strict config validation, manifest-backed artifact provenance, plugin-only model selection, public/private artifact boundaries, and survival verdict semantics. This issue should not reopen those contracts. It should make the CLI a thin, modular, agent-safe entry point over them.

---

## Actors

- A1. Experiment iteration agent: Repeatedly edits experiment settings, runs training/evaluation, reads structured results, and decides what to try next.
- A2. Local researcher: Runs experiments manually and wants concise command behavior without losing reproducibility.
- A3. CI or automation runner: Executes CLI commands non-interactively and needs stable process behavior and parseable output.
- A4. CLI maintainer: Adds future commands without growing a monolithic runner or duplicating output/error/default handling.
- A5. Run reviewer: Reads manifests and artifacts later and needs to understand whether local defaults affected a run.

---

## Key Flows

- F1. Run an explicit experiment with JSON output
  - **Trigger:** An agent or CI calls `aerd run <experiment-config> --json`.
  - **Actors:** A1, A3, A5
  - **Steps:** Resolve the explicit config, validate it through the existing config/model registry boundary, execute the full experiment pipeline including split-local model training, write manifest-backed artifacts, and emit a stable redacted JSON result.
  - **Outcome:** The command exits according to execution success, and the agent can parse run id, status, manifest/report locations, verdict information, warnings, and safe summaries without scraping text.
  - **Covered by:** R1, R2, R5, R6, R7, R8, R9, R10, R11
- F2. Run the local default experiment
  - **Trigger:** A user or agent calls `aerd run --json` without passing an experiment config.
  - **Actors:** A1, A2, A5
  - **Steps:** Resolve the local private default experiment, fail fast if no default is configured or it cannot be used, otherwise run the selected experiment exactly as an explicit config run and record that the default supplied the config.
  - **Outcome:** Repeated local iteration is low-friction, but the applied default is visible in JSON output and run evidence.
  - **Covered by:** R3, R4, R5, R8, R10, R12, R13, R14
- F3. Set the local default experiment
  - **Trigger:** A user or agent calls `aerd exp defaults set <experiment-config>`.
  - **Actors:** A1, A2, A4
  - **Steps:** Validate the provided experiment reference enough to avoid storing unusable local state, write the local private default, and report the resulting default in a parseable command result.
  - **Outcome:** Future `aerd run` calls without a config have an intentional default experiment source.
  - **Covered by:** R3, R4, R12, R13, R15
- F4. Add or maintain CLI commands modularly
  - **Trigger:** A maintainer adds `run`, `exp defaults`, or future command namespaces.
  - **Actors:** A4
  - **Steps:** Add command-specific parser/handler logic behind the root `aerd` dispatcher, use shared JSON/error/default/redaction behavior, and keep experiment business logic inside existing domain APIs rather than inside CLI parsing code.
  - **Outcome:** The CLI grows by adding isolated commands instead of turning the root runner into a second orchestration layer.
  - **Covered by:** R16, R17, R18, R19, R20

---

## Requirements

**Canonical command surface**
- R1. `aerd` must be the canonical installed command prefix for the research CLI; new docs and examples should prefer `aerd` over module invocation.
- R2. The MVP command surface must include `aerd run [experiment-config]` with optional `--json` output.
- R3. The MVP command surface must include `aerd exp defaults set <experiment-config>` for setting the local default experiment used by `aerd run` when no config is passed.
- R4. `aerd exp defaults set` must not edit the experiment YAML itself; it manages local default selection state for future runs.

**Run selection and defaults**
- R5. When `aerd run` receives an explicit experiment config, that explicit config must win over any local default.
- R6. When `aerd run` receives no experiment config, it must use the configured local default experiment if one exists and is usable.
- R7. When no experiment config is passed and no usable local default exists, the CLI must fail fast before creating run artifacts or starting data/model work.
- R8. Runs that use a local default must make the selected config source visible in the command result and in run provenance evidence.
- R9. Static config and registry validation must still complete before run directory creation for failures that can be detected before execution.

**Agent-safe JSON output**
- R10. `aerd run --json` must emit stable, redacted, machine-readable output suitable for agents and CI; agents must not need to scrape the human output path.
- R11. Successful run JSON must include enough safe information for the next agent action: run identity, lifecycle status, manifest path, report artifact/path reference, report verdict/status, concise gate/reason summary, warnings or provider/data-quality state when present, model plugin identity, and a small artifact summary.
- R12. CLI JSON must identify whether the run used an explicit config or the local default, without dumping raw configs, secrets, trusted native state, large tables, or proprietary result payloads.
- R13. Failure JSON must distinguish default-resolution failures, config/registry validation failures, execution failures after a manifest exists, user interruption, and unexpected internal errors.
- R14. If a failure happens after a manifest-backed run has started, JSON output must include the safe run/manifest reference so agents can inspect preserved failed-run evidence.

**Exit behavior**
- R15. A completed experiment run must exit `0` even when the survival report verdict is rejected or inconclusive; research verdicts are results to parse, not process execution failures.
- R16. Invalid invocation, missing local default, invalid config, plugin/registry validation failure, execution failure, user interruption, and internal error must have documented non-zero behavior stable enough for agents and CI.
- R17. The MVP must not require a verdict-failing CI mode by default; a future flag may add that behavior without changing normal experimentation semantics.

**Modular CLI architecture**
- R18. The root `aerd` CLI must act as a thin dispatcher rather than owning experiment orchestration, defaults persistence, JSON formatting, and command-specific behavior in one monolithic function.
- R19. Each command or command namespace must have isolated parser/handler ownership so adding a future command does not require modifying the internals of `run`.
- R20. Shared CLI infrastructure must own cross-cutting concerns once: JSON serialization, redaction, error-to-exit mapping, local default resolution, and user-facing command result formatting.
- R21. CLI command handlers must call domain-level experiment/config APIs rather than duplicating config validation, model training, artifact writing, or report interpretation logic.
- R22. Exact module names and file layout are planning decisions, but the architecture must preserve a clear separation between command routing, command behavior, shared CLI infrastructure, and research-domain execution.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R10, R11.** Given a valid experiment config is passed to `aerd run <experiment-config> --json`, when the run completes, stdout contains a stable JSON result with run/report/provenance summary fields and the process exits `0`.
- AE2. **Covers R3, R4, R6, R8.** Given `aerd exp defaults set <experiment-config>` has configured a local default, when `aerd run --json` is called without a config, the CLI runs that default experiment and records that the config came from the local default.
- AE3. **Covers R5.** Given a local default exists, when `aerd run <different-experiment-config> --json` is called, the explicit config is used and the local default is not applied.
- AE4. **Covers R7, R13, R16.** Given no local default exists, when `aerd run --json` is called without a config, the command fails before creating run artifacts and emits a structured default-missing failure.
- AE5. **Covers R9, R13, R16.** Given the selected config references an unknown model plugin, when `aerd run --json` validates it, the command fails before creating a run directory and reports a config/registry validation failure.
- AE6. **Covers R14.** Given a run fails after the manifest is initialized, when `aerd run --json` returns failure output, the JSON includes a safe manifest reference and the failed run evidence remains inspectable.
- AE7. **Covers R15, R17.** Given a run completes and the survival report verdict is rejected, when `aerd run --json` exits, the process exit code is still `0` and the rejected verdict is represented in JSON.
- AE8. **Covers R18, R19, R20, R21.** Given a maintainer adds a future command namespace, when the command is implemented, it uses the shared output/error/default infrastructure and does not place new experiment orchestration logic in the root dispatcher.

---

## Success Criteria

- Agents can run experiments repeatedly through `aerd run --json`, parse results deterministically, and decide whether to adjust indicators, config, thresholds, or model settings next.
- Local researchers can set a default experiment once and run it repeatedly without hiding that default from run evidence.
- Completed research verdicts are separated cleanly from process failures, so rejected or inconclusive experiments remain useful iteration results.
- CLI maintainers can add new commands under `aerd` without growing a monolithic `cli.py` or duplicating JSON/error/default behavior.
- Planning can proceed without inventing command naming, default application semantics, exit-code philosophy, JSON output purpose, or modularity goals.

---

## Scope Boundaries

- Do not add `validate`, `dry-run`, broad preflight, provider-check, or strict-warning command modes in this MVP.
- Do not make survival verdict rejection or inconclusive evidence fail the process by default.
- Do not add project-shared defaults, named profiles, layered config overlays, or team-level default management in this issue.
- Do not add a full human CLI redesign, interactive prompts, quiet/verbose modes, or rich terminal UI.
- Do not duplicate `manifest.json` as a full artifact inventory in CLI JSON; the CLI returns a summary and safe pointers, while the manifest remains authoritative.
- Do not print credentials, raw configs, secret-like values, proprietary tables, trusted plugin-native state contents, or large artifacts by default.
- Do not add backward-compatible aliases such as `aegis-rd` unless planning discovers a concrete consumer that already depends on one.
- Do not choose exact module names, local-default storage paths, JSON field names, or numeric exit-code values during brainstorming.

---

## Key Decisions

- Canonical executable is `aerd`: The shorter command is better for agents, scripts, docs, and future command namespaces than `aegis-rd`.
- Experiment defaults live under `exp defaults`: The command manages experiment run selection, not general tool preferences or direct YAML editing.
- Local private defaults in v1: Defaults are for personal/agent iteration on the current machine, not shared project state or profiles.
- Explicit config wins: Passing a config to `aerd run` must remain unambiguous even when a local default exists.
- Run-first MVP: The first agent UX improvement should optimize the full execution path that trains models and produces evidence, rather than adding validation/preflight commands first.
- JSON summary, not manifest clone: `run --json` should contain enough for immediate agent decisions while preserving `manifest.json` as the detailed source of truth.
- Verdicts are not process failures: Rejected or inconclusive survival results are valid experiment outcomes and should not break iteration loops by default.
- Modular CLI from this point forward: The issue should create a command architecture that future CLI work can extend without rewriting the runner.

---

## Dependencies / Assumptions

- `research/aegis_research/cli.py` is the current CLI entry point and currently contains a single `run` command.
- `pyproject.toml` currently does not define an installed console script, so `aerd` is new public CLI surface.
- The existing config contract in `docs/brainstorms/2026-05-16-experiment-config-contract-requirements.md` defines strict side-effect-free config validation that `aerd run` should reuse.
- The provenance contract in `docs/brainstorms/2026-05-16-experiment-provenance-contract-requirements.md` defines manifest-backed run identity, artifact inventory, failed-run evidence, and public/private artifact boundaries that CLI output should summarize rather than replace.
- The model plugin contract in `docs/brainstorms/2026-05-17-model-plugin-target-probability-contract-requirements.md` and `docs/model-plugins.md` define plugin-only model execution and the default registry behavior that CLI config validation must respect.
- The report contract in `docs/brainstorms/2026-05-18-report-metrics-survival-verdict-contract-requirements.md` defines survival verdict states that `aerd run --json` should expose without converting ordinary rejected results into process failures.
- Current `run_experiment` behavior trains models inside the full run path, per validation split, after data, labels, features, and split evidence are prepared.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R18, R19][Technical] What exact Python entry point and module layout should expose `aerd` while keeping command routing thin and command handlers isolated?
- [Affects R3, R4, R6, R7, R8][Technical] Where should local private experiment defaults be stored, and how should invalid, deleted, or moved default experiment paths fail?
- [Affects R10, R11, R12, R13, R14][Technical] What exact JSON result shape best balances stable agent parsing with avoiding a second manifest schema?
- [Affects R13, R16][Technical] Which exact named error categories and numeric exit codes should represent invocation, default, config, registry, execution, interruption, and internal failures?
- [Affects R20][Technical] What shared redaction/output boundary should CLI JSON use so it stays consistent with existing config and artifact redaction rules?

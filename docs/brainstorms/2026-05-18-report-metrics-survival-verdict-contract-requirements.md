---
date: 2026-05-18
topic: report-metrics-survival-verdict-contract
github_issue: 10
---

# Report Metrics And Survival Verdict Contract

## Summary

Issue #10 will keep VectorBT as the metric calculation engine while making Aegis own the survival verdict contract. Reports should preserve metric settings, availability, warnings, split evidence, and structured gate outcomes so a research run can be clearly marked as survived, rejected, or inconclusive from trustworthy out-of-sample evidence.

---

## Problem Frame

`research/aegis_research/reports.py` turns portfolios, validation metrics, and split metadata into the pass/fail artifact for a research run. That makes report generation part of the research correctness boundary, not only a presentation layer.

The current report path already uses VectorBT portfolio stats for core metrics and records some decision-grade validation metadata. It also still carries ambiguous survival semantics: display-title extraction can couple the normalized report to VectorBT presentation labels, aggregate split summaries can drive verdicts even though they are labeled descriptive, missing metrics become plain threshold failures, and the final reasons are unstructured strings rather than auditable gate records.

VectorBT is the right engine for computing portfolio, trade, return, drawdown, benchmark, and uncertainty metrics. It does not decide whether an Aegis validation run is decision-grade, whether purged split evidence is sufficient, whether a missing Sharpe ratio is a failure or unavailable evidence, or whether split-level evidence supports survival. Those trust and verdict decisions belong to Aegis.

---

## Actors

- A1. Experiment author: Configures and runs research experiments, then reads the survival report to decide whether a strategy deserves more investigation.
- A2. Validation stage: Produces per-split train/test portfolios, metrics, split metadata, and decision-grade evidence.
- A3. Report stage: Normalizes VectorBT metric outputs and produces the survival report artifact.
- A4. Reviewer or automation agent: Audits reports for reproducibility, evidence quality, and survival-gate meaning without re-running the experiment.
- A5. Future planner or maintainer: Evolves metric and gate behavior while preserving a clear forward-first contract.

---

## Key Flows

- F1. Compute and normalize portfolio metrics
  - **Trigger:** A portfolio or split portfolio is ready for reporting.
  - **Actors:** A2, A3
  - **Steps:** Request required metrics from VectorBT by metric identity, apply explicit frequency/year-frequency and benchmark assumptions, capture metric availability or warnings, and normalize values for aggregate and per-symbol views.
  - **Outcome:** Report metrics are reproducible, traceable to VectorBT settings, and not dependent on display-label lookups alone.
  - **Covered by:** R1, R2, R3, R4, R5, R6
- F2. Evaluate survival gates from split-first evidence
  - **Trigger:** Validation has produced out-of-sample split evidence and a survival report is requested.
  - **Actors:** A2, A3, A4
  - **Steps:** Treat per-split test metrics as the decision source, evaluate each configured gate with value, threshold, comparator, source, and evidence status, and keep aggregate metrics as labeled summaries.
  - **Outcome:** A reader can see exactly why a run survived, failed, or lacked enough evidence.
  - **Covered by:** R7, R8, R9, R10, R11, R12, R13
- F3. Preserve report provenance and diagnostics
  - **Trigger:** The survival report artifact is written.
  - **Actors:** A3, A4, A5
  - **Steps:** Persist metric settings, benchmark/frequency assumptions, split aggregation policy, metric warnings, gate outcomes, and validation metadata alongside train/test metrics.
  - **Outcome:** The report is deterministic and auditable without requiring private VectorBT objects.
  - **Covered by:** R14, R15, R16, R17, R18

---

## VBT Evidence Used

- `StatsBuilderMixin.stats` accepts metric keys, `settings`, `metric_settings`, `filters`, `agg_func`, `group_by`, and warning controls. `agg_func=None` returns per-column or per-group stats rather than a single aggregate.
- `Portfolio.metrics` exposes stable metric identities such as `total_return`, `bm_return`, `max_dd`, `total_trades`, `win_rate`, `profit_factor`, `expectancy`, `sharpe_ratio`, `calmar_ratio`, `omega_ratio`, and `sortino_ratio`.
- VectorBT docs and support examples show users commonly requesting metrics by keys and inspecting results such as Sharpe ratio, max drawdown, total trades, win rate, expectancy, and total return across columns, parameter combinations, or splits.
- VectorBT support guidance for multi-metric cross-validation selection says the caller must provide a selection function. That means Aegis should not imply VectorBT supplies the survival policy.
- Frequency and year-frequency affect annualized metrics. VectorBT may infer frequency in newer versions, but if frequency cannot be parsed, annualized metrics can be skipped or warned.
- `Portfolio.returns_stats` provides a return-risk-focused stats surface including annualized return/volatility, drawdown, Sharpe, Calmar, Omega, Sortino, tail metrics, alpha, and beta.
- `Portfolio.get_prob_sharpe_ratio` and `Portfolio.get_deflated_sharpe_ratio` exist and are useful uncertainty diagnostics, especially for parameter sweeps or many-column comparisons. Support examples show deflated Sharpe can be `NaN` and is mainly useful with many columns/trials, so it should not be mandatory for every first-pass survival verdict.

---

## Requirements

**VectorBT Metric Contract**
- R1. Report metric calculation must use VectorBT as the canonical metric engine for portfolio, trade, return, drawdown, benchmark, and supported uncertainty metrics unless a metric is explicitly outside VectorBT's scope.
- R2. Required report metrics must be requested by VectorBT metric identity rather than relying on display-title lookups as the source of truth.
- R3. The normalized report must preserve the project-owned metric names used by downstream Aegis code while recording the VectorBT metric identities and settings that produced them.
- R4. Frequency and year-frequency assumptions must be explicit for annualized metrics such as Sharpe, Calmar, Omega, and Sortino.
- R5. Benchmark-dependent metrics must record whether benchmark evidence was available, unavailable, or intentionally not configured, and must not silently imply benchmark-relative evidence when no benchmark exists.
- R6. Metric warnings, skipped metrics, unavailable metrics, non-finite values, and degenerate metric conditions must be visible in report evidence rather than silently collapsing into `None` without context.

**Split Metrics And Aggregation**
- R7. Per-split test metrics must remain first-class report evidence for validation runs.
- R8. Aggregate metrics must be labeled as descriptive summaries unless the contract explicitly defines them as gate inputs.
- R9. Split aggregation policy must be recorded per metric, including whether the policy is mean, median, max, min, sum, duration-weighted, percentile-based, or not aggregated.
- R10. Ratio-like metrics such as return, Sharpe, win rate, profit factor, and expectancy must not be silently averaged into decision evidence without a declared policy and rationale.
- R11. Per-symbol metric evidence must preserve enough split and symbol identity for reviewers to diagnose whether a headline result hides weak symbols or weak splits.
- R12. Train metrics may be reported for diagnostics, but survival decisions must come from out-of-sample test evidence.

**Survival Verdict Gates**
- R13. Survival verdicts must be produced from structured gate outcomes rather than only from free-form reason strings.
- R14. Each gate outcome must record the source metric, source evidence scope, actual value or availability state, threshold, comparator, status, and reason.
- R15. Gate statuses must distinguish pass, fail, insufficient evidence, unavailable metric, and invalid or non-decision-grade validation.
- R16. `needs_more_evidence` or an equivalent inconclusive state must be reserved for evidence-quality gaps such as insufficient trades, unavailable required metrics, invalid validation metadata, or non-decision-grade split evidence.
- R17. Clear metric threshold failures with decision-grade evidence should reject the run rather than being conflated with insufficient evidence.
- R18. A run may survive only when required decision-grade gates pass and no required gate is unavailable, invalid, or inconclusive.

**Uncertainty And Robustness Evidence**
- R19. Probabilistic Sharpe, deflated Sharpe, confidence intervals, split pass rates, or similar uncertainty evidence should be recorded when available and relevant.
- R20. Uncertainty metrics must be optional diagnostic evidence in the first issue #10 contract unless the experiment shape explicitly makes them required.
- R21. If uncertainty metrics are unavailable, unsupported, non-finite, or inappropriate for the portfolio shape, the report must record that availability state without failing otherwise valid survival gates solely for that absence.

**Artifact And Provenance Contract**
- R22. The survival report artifact must include metric settings, frequency/year-frequency assumptions, benchmark assumptions, split aggregation policy, metric availability, metric warnings, validation metadata, and structured gate outcomes.
- R23. The report must make the role of aggregate metrics explicit so downstream readers do not mistake descriptive summaries for decision evidence.
- R24. The report artifact must remain schema-versioned and deterministic enough for automation to compare reports across runs.
- R25. Human-readable reasons may remain, but they must be derived from or consistent with structured gate outcomes rather than being the only verdict evidence.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R6.** Given a portfolio report requests total return, max drawdown, total trades, win rate, fees, and Sharpe, when metrics are produced, the report records normalized Aegis names plus the VectorBT metric identities/settings and exposes any unavailable or warned metric.
- AE2. **Covers R4, R6, R15, R16.** Given Sharpe is a required survival gate and frequency/year-frequency evidence is missing or invalid, when the report is built, the Sharpe gate is marked unavailable or invalid and the verdict is inconclusive rather than a plain threshold failure.
- AE3. **Covers R5, R19, R20, R21.** Given no benchmark was configured, when benchmark-relative metrics or uncertainty diagnostics are unavailable, the report records the benchmark status and diagnostic availability without implying benchmark evidence or automatically rejecting a run for optional diagnostics.
- AE4. **Covers R7, R8, R9, R10, R12, R13.** Given validation produces multiple purged test splits, when survival gates are evaluated, per-split test evidence drives the gate outcomes and aggregate metrics are labeled with their descriptive aggregation policy.
- AE5. **Covers R14, R15, R16, R17, R18.** Given decision-grade split evidence and required metrics are available, when Sharpe fails the configured threshold, the report records a structured failed gate and marks the run rejected rather than inconclusive.
- AE6. **Covers R14, R15, R16.** Given total trades are below the minimum evidence threshold, when the report is built, the trade gate records actual trades, required trades, comparator, and insufficient-evidence status, and the verdict is inconclusive.
- AE7. **Covers R22, R23, R24, R25.** Given a survival report is written, when automation reads the artifact, it can identify the schema version, metric settings, split aggregation policy, gate outcomes, and human-readable reasons without loading private VectorBT objects.

---

## Success Criteria

- Experiment authors can trust that a survival verdict means the right kind of evidence passed, failed, or was unavailable, not merely that aggregate numbers happened to cross thresholds.
- Reviewers can audit metric source, settings, warnings, benchmark/frequency assumptions, split evidence, and gate outcomes from `survival_report.json` without re-running the experiment.
- VectorBT remains the authoritative computation engine for supported metrics while Aegis owns the research trust policy around those metrics.
- Planning can proceed without inventing verdict states, gate evidence semantics, split aggregation meaning, optional uncertainty behavior, or report provenance expectations.

---

## Scope Boundaries

- Do not replace VectorBT portfolio, trade, return, drawdown, benchmark, or uncertainty metric calculation with broad custom Aegis metric implementations.
- Do not make probabilistic or deflated Sharpe mandatory hard gates for every survival report in the first issue #10 contract.
- Do not build a full research-methodology framework for statistical significance, multiple-hypothesis correction, or live-trading readiness in this issue.
- Do not decide exact class names, JSON field names, file layout, or migration mechanics during brainstorming.
- Do not make train metrics part of survival decisions; train metrics remain diagnostics.
- Do not add backward-compatibility shims for pre-contract survival reports unless planning identifies a concrete consumer that requires them.

---

## Key Decisions

- VectorBT metrics plus Aegis gates: VectorBT should compute metrics, but Aegis must own verdict semantics, evidence quality, and decision-grade trust.
- Split-first verdicts: Per-split test evidence is the survival source of truth; aggregate metrics are summaries unless explicitly declared otherwise.
- Structured outcomes over reason strings: Human reasons are useful, but automation and reviewers need machine-readable gate records.
- Inconclusive is distinct from rejected: Missing or insufficient evidence should not be treated the same as a valid metric failing a threshold.
- Optional uncertainty evidence: Probabilistic and deflated Sharpe are valuable diagnostics, especially for parameter sweeps, but they are not universal hard gates for the first contract.

---

## Dependencies / Assumptions

- Issue #3's purged validation contract defines the split evidence and decision-grade metadata that this report contract consumes.
- Issue #8's provenance contract defines broader artifact manifest expectations; this issue should align survival report artifacts with that direction rather than inventing a separate provenance model.
- The current report boundary is `research/aegis_research/reports.py`, with validation aggregation feeding it from `research/aegis_research/validation.py` and report artifact writing in `research/aegis_research/provenance/experiment_artifacts.py`.
- The current config contract already requires positive, parseable report frequency values through `ReportConfig`; issue #10 may need to sharpen how those settings are carried into VectorBT stats and report evidence.
- VectorBT PRO behavior cited here is from available docs/API/support evidence as of 2026-05-18.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R2, R3, R22][Technical] What exact normalized metric catalog should issue #10 expose, and how should each normalized name map to VectorBT metric identities and methods?
- [Affects R7, R8, R9, R10, R13][Technical] What exact split-first gate policy should be used for each configured survival threshold: every split must pass, worst split must pass, pass rate must exceed a threshold, or a hybrid policy?
- [Affects R14, R15, R24][Technical] What schema version and concrete gate-outcome shape should represent pass, fail, insufficient evidence, unavailable metric, invalid validation, and optional diagnostics?
- [Affects R5, R19, R20, R21][Needs research] Which benchmark-relative and uncertainty metrics should be in the first optional diagnostic set, and under which experiment shapes are they meaningful enough to compute?
- [Affects R6, R22][Technical] How should VectorBT warnings be captured reliably without suppressing useful warnings or leaking noisy implementation details into stable artifacts?

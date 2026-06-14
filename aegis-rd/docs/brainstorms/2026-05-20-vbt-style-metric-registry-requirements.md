---
date: 2026-05-20
topic: vbt-style-metric-registry
---

# VBT-Style Metric Registry

## Summary

Introduce a dedicated metric registry architecture that keeps ranking config VBT-style while separating metric definitions from config validation, reports, and run orchestration. Dynamically discovered native VBT stats metrics and trusted Aegis/custom VBT-style metrics share one global metric ID namespace, and leaderboards render the primary metric plus required secondary metrics through a uniform metrics map.

---

## Problem Frame

Experiment configs currently express ranking with Aegis-normalized metric names such as `total_return_pct`, while the desired config surface should use VBT-native metric IDs in the same spirit as exact VBT data-column names.

The first custom metric should stay narrow: `baseline_delta` is a contextual leaderboard metric computed from the selected primary metric and trusted baseline payloads. Broader train-lane feature-quality metrics can be added later through the same trusted registry API once their formulas and input contracts are settled.

Without a separate metric registry boundary, adding metrics would keep pulling metric catalog knowledge into main config, report, and run files. That makes custom metrics expensive to add and increases the chance that ranking, report, and artifact behavior diverge.

---

## Actors

- A1. Config author: Selects primary and secondary metrics in experiment YAML using stable metric IDs.
- A2. Metric author: Adds native VBT or custom VBT-style metrics without editing unrelated orchestration files.
- A3. Experiment runner: Validates metric selections before side effects and computes required metric values before publishing completed leaderboards.
- A4. Leaderboard consumer: Reads ranked results without needing to know whether each metric was native VBT or custom Aegis-registered logic.
- A5. Planning or automation agent: Extends, validates, or compares metric behavior using registry metadata and stable artifacts.

---

## Key Flows

- F1. Register trusted metrics
  - **Trigger:** A run or train lane is prepared for config resolution.
  - **Actors:** A2, A3, A5
  - **Steps:** Compose the built-in metric registry, dynamically discover/register supported native VBT metrics from VBT stats targets, register built-in custom metric plugins through a generic custom-metrics composition point, optionally register trusted project/custom providers, then freeze the registry before validation.
  - **Outcome:** Config validation and execution see one immutable metric catalog with stable IDs and provenance.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9
- F2. Validate ranking selection
  - **Trigger:** A config containing a ranking block is loaded.
  - **Actors:** A1, A3, A5
  - **Steps:** Resolve the primary metric and secondary metrics against the global registry, reject duplicates, check lane support, and defer only data-dependent availability checks to runtime preflight.
  - **Outcome:** Unknown or impossible metric selections fail before run side effects.
  - **Covered by:** R13, R14, R15, R16, R17, R18, R20, R21
- F3. Publish leaderboard metric values
  - **Trigger:** Candidate scoring completes for a ranked result set.
  - **Actors:** A3, A4, A5
  - **Steps:** Compute the primary and secondary metrics, including contextual secondary metrics such as `baseline_delta` when selected, fail if any required metric is unavailable, sort rows by the selected primary metric and direction, and publish each row with a uniform metrics map.
  - **Outcome:** Leaderboard rows are comparable across native and custom metrics, and incomplete metric evidence cannot look like a completed run.
  - **Covered by:** R10, R16, R22, R23, R25, R26, R27, R28

---

## Conceptual Architecture

The metric registry should live behind a dedicated package boundary so metric definitions can grow without changing unrelated main files:

```text
research/aegis_research/metrics/
  __init__.py               # make_default_metric_registry()
  contracts.py              # MetricDefinition, source types, lane/input metadata
  registry.py               # MetricRegistry, FrozenMetricRegistry, fingerprinting
  stats.py                  # dynamic VBT stats metric discovery
  validation.py             # lane support and input availability checks
  adapters.py               # VBT StatsBuilder/custom-metric target adapters
  custom/
    __init__.py             # composition point: register_custom_metrics(registry)
    baseline_delta.py       # contextual secondary metric against configured baseline
```

The custom-metrics area is intentionally generic rather than named after one metric family. `baseline_delta` is the initial built-in custom metric, and the same structure should support future VBT-friendly metrics after their semantics are planned.

Custom project metrics may live outside this package, but they must enter through the same trusted registry API before config resolution. Experiment YAML selects metric IDs only; it must not define metric code, import paths, or calculation functions.

---

## Requirements

**Metric Registry Architecture**
- R1. Metric definitions and registry contracts must live behind a dedicated metrics package boundary instead of being owned by config, report, or run orchestration modules.
- R2. The registry must support native VBT metrics and trusted custom VBT-style metrics under one global string ID namespace.
- R3. Metric IDs must be globally unique; duplicate registration must fail before config resolution.
- R4. Metric definitions must include enough metadata to validate and explain the metric, including ID, display title, unit or value semantics, source type, supported lanes, primary/secondary eligibility, direction hint, and required inputs.
- R5. The registry must be freezeable before config resolution so validation and execution use an immutable metric snapshot.
- R6. The frozen registry must expose stable provenance suitable for run evidence, such as a fingerprint or equivalent registry identity.
- R7. Custom metric providers must register trusted Python metric definitions through a registry API before config resolution; YAML must remain declarative and inert.
- R8. Adding a custom metric must not require editing main config validation, report generation, leaderboard construction, or lane orchestration files.
- R9. Built-in native VBT metrics must be dynamically registered from supported VBT stats targets using their native metric IDs, similar to how data providers are discovered from VBT `*Data` classes.
- R10. Built-in custom metrics such as `baseline_delta` must be represented as custom VBT-style metric plugins rather than assumed to be built-in VBT portfolio stats or special rank modes.
- R11. Each built-in custom metric plugin must live in its own file under the generic custom-metrics package and be collected by its composition point.
- R12. Custom metric plugins should use VBT's generic StatsBuilder/custom-metric shape when their target object supports `stats()`, and otherwise provide an Aegis adapter that exposes the relevant lane data as a VBT-compatible metric target.
- R13. Config authors must call native and custom metrics by name only, for example `metric: total_return` or `secondary_metrics: [baseline_delta]`; they must not specify the metric implementation source.

**Ranking Config Contract**
- R14. Ranking config must select one primary-eligible metric by VBT-style metric ID string.
- R15. Ranking config must keep `direction` explicit as Aegis leaderboard sort policy, with `desc` meaning larger values rank higher and `asc` meaning smaller values rank higher.
- R16. Ranking config must support `secondary_metrics` as an optional list of secondary-eligible VBT-style metric ID strings that are displayed on leaderboard rows but do not affect ordering.
- R17. Ranking config must be strings-only for metric selection; per-metric settings, calculation functions, import paths, implementation source fields, and object-shaped metric entries do not belong in the ranking block.
- R18. The primary metric must not appear in `secondary_metrics`, and duplicate secondary metrics must be rejected.
- R19. Existing Aegis-normalized metric names such as `total_return_pct` are not part of the target config contract unless a separate migration decision explicitly adds aliases.

**Validation And Execution**
- R20. Config validation must reject metric IDs that are not present in the global frozen registry.
- R21. Config validation must reject registered metrics that can never be computed for the selected lane.
- R22. Runtime publication must reject registered and lane-supported metrics when required data-dependent inputs are missing, such as trusted baseline metric values, benchmark returns, or frequency assumptions.
- R23. Primary and secondary metrics must be required outputs for a completed leaderboard; missing values must fail the run or preflight rather than produce null completed rows.
- R24. Metric-specific parameters for custom metrics must come from the owning lane configuration or metric provider defaults rather than the ranking block.

**Leaderboard Artifact Contract**
- R25. Leaderboard metadata must declare the primary metric, direction, selected secondary metrics, and the metric registry identity used for validation and computation.
- R26. Leaderboard rows must expose a single `metrics` map containing the primary metric value and all selected secondary metric values.
- R27. Leaderboard ordering must be determined by the selected primary metric and direction; `baseline_delta` is a contextual secondary metric and must not become a primary ranking target or separate `rank_by` mode.
- R28. Leaderboard consumers must be able to read metric values without special-casing whether the metric came from native VBT stats or custom Aegis-registered logic.

---

## Acceptance Examples

- AE1. **Covers R2, R3, R20.** Given a config selects an unregistered metric ID, when config validation runs, it fails before data fetches, model training, portfolio simulation, or artifact writes.
- AE2. **Covers R13, R14, R16, R18.** Given a config lists the primary metric again in `secondary_metrics`, when config validation runs, it rejects the duplicate instead of silently deduplicating.
- AE3. **Covers R21.** Given a trusted project provider registers a metric that cannot run in the selected lane, when validation can determine the lane cannot compute it, validation fails at the config boundary.
- AE4. **Covers R22, R23.** Given a config selects `baseline_delta` as a secondary metric but a candidate lacks trusted baseline metric values, runtime publication fails before producing a completed leaderboard.
- AE5. **Covers R7, R8.** Given a trusted project metric provider registers `my_alpha_score` before config resolution, when a config selects that metric, validation can accept it without edits to main config, report, leaderboard, or orchestration files.
- AE6. **Covers R10, R11, R12.** Given a new built-in custom metric is added, when it is implemented, it lives in its own custom metric plugin file and either uses VBT StatsBuilder on a compatible target or provides an Aegis target adapter.
- AE7. **Covers R9, R13.** Given VBT exposes a supported native metric such as `total_return`, when the default metric registry is composed, the metric can be selected by name in config without declaring an implementation source.
- AE8. **Covers R25, R26, R28.** Given a leaderboard ranks by `total_return` and selects `sharpe_ratio` and `max_dd` as secondary metrics, when rows are published, each row contains one metrics map with all three values and consumers do not need flat top-level metric fields.
- AE9. **Covers R15, R27.** Given a leaderboard ranks by `max_dd` with `direction: asc`, when rows are sorted, smaller drawdown values rank higher while secondary metrics remain display-only.
- AE10. **Covers R10, R16, R27.** Given a playbook or strategy defines a baseline and config includes `baseline_delta` in `secondary_metrics`, when leaderboard rows are published, `baseline_delta` is computed against the selected primary metric's baseline and ordering still follows the primary metric plus direction.

---

## Success Criteria

- Config authors can use VBT-style metric IDs consistently for primary and secondary ranking metrics.
- Metric authors can add trusted custom metrics through a metric provider or dedicated metric module without editing unrelated main files.
- Unknown, duplicate, lane-incompatible, or input-incomplete metrics fail before a completed leaderboard can be published.
- Leaderboard consumers receive one predictable metric-value shape for native and custom metrics.
- A planner can implement the metric registry boundary without inventing the config contract, failure semantics, leaderboard row shape, or scope boundaries.

---

## Scope Boundaries

- No inline Python, import paths, custom calculation functions, or metric object definitions in experiment YAML.
- No arbitrary runtime custom metrics that have not been registered through a trusted metric registry.
- No requirement to preserve old normalized config metric aliases such as `total_return_pct` unless a separate migration decision adds that compatibility work.
- No secondary-metric ordering, weighted composite scoring, tie-break policies, or multi-objective optimization in this scope.
- No separate `rank_by` special mode for baseline delta; baseline comparison belongs in the single contextual secondary metric `baseline_delta`.
- No flat metric columns on leaderboard rows; the target row shape is a metrics map.
- No train-lane custom metric families in this scope; feature-quality metrics need their own requirements before becoming built-ins.
- No broad redesign of all report outputs beyond making metric selection and leaderboard values registry-backed.

---

## Key Decisions

- Dedicated metrics package: Metric catalogs and metric extension APIs belong behind `research/aegis_research/metrics/`, not in report or config main files.
- Generic custom metrics composition point: Custom metric modules are collected through a generic `custom` module instead of a domain-specific module such as `feature_quality`.
- Dynamic native metric registration: Built-in VBT metrics are discovered and registered by native metric name, mirroring the data-provider pattern, instead of requiring users to identify an implementation module in config.
- One custom metric per plugin file: Built-in custom VBT-style metrics should be isolated by metric so each can evolve independently.
- Baseline comparison as one metric: Useful baseline-delta behavior should be preserved as a single contextual secondary metric named `baseline_delta`, not as per-primary metric IDs or a parallel ranking mechanism.
- Global metric namespace: Native VBT and custom VBT-style metrics share one registry and one string ID namespace.
- Trusted provider extension: Custom metrics are added by registering trusted Python definitions before config resolution, not by making YAML executable.
- Strings-only ranking: Ranking config selects metric IDs only; metric settings live in the lane or provider contract.
- Two-stage failure: Unknown and impossible metrics fail at config validation; missing data-dependent inputs fail during runtime preflight before completed output.
- Uniform row values: Leaderboard rows expose primary and secondary metric values through a single metrics map.

---

## Dependencies / Assumptions

- VectorBT PRO supports custom stats metrics through generic StatsBuilder metric definitions with calculation functions, so Aegis custom metrics can stay VBT-style even when they are not built-in native stats metrics or not computed on `Portfolio`.
- Several VBT object types expose `stats()`, so custom metric plugins should declare their expected metric target rather than assuming every custom metric runs through `Portfolio.stats()`.
- Existing registry patterns, such as model plugin registration and frozen registry snapshots, are suitable precedent for metric registry composition and provenance.
- Some future custom metrics may need lane-produced inputs such as feature matrices, labels, forward returns, split metadata, benchmark returns, or target schema before they can be computed reliably.
- The project prefers fail-fast, declarative config and trusted-code extension points over permissive runtime discovery or YAML-executed behavior.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R4][Technical] What exact dataclass or protocol shape should represent metric definitions, lane support, source type, and required inputs?
- [Affects R7, R8][Technical] Should external metric providers be registered explicitly by callers, discovered through package entry points, or loaded through a repo-local provider convention?
- [Affects R9, R20][Technical] Which VBT stats targets and native metric IDs are supported by the first dynamic native registration pass?
- [Affects R10, R12, R22][Needs research] What future custom metric families should be promoted to built-ins after their formulas, horizons, grouping, aggregation rules, and VBT-compatible target adapters are defined?
- [Affects R10, R27][Technical] What exact value semantics should `baseline_delta` expose in the metrics map versus evidence, especially raw delta versus direction-adjusted improvement?
- [Affects R22, R24][Technical] Which lane configuration fields own custom metric inputs such as forward-return horizon, label target definition, benchmark returns, and split aggregation?
- [Affects R25][Technical] What registry fingerprint and metric-definition evidence should be persisted in run artifacts?
- [Affects R19][Technical] How should existing normalized portfolio metric keys be removed or migrated in tests, examples, and docs?

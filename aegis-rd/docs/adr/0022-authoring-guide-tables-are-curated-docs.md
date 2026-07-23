# Authoring-guide manifest tables are curated docs, not a duplication smell

Status: accepted

The manifest field tables in `component_registry/authoring/strategy_guide.py` and
`indicator_guide.py` (`_manifest_field_table()`) are deliberately hand-authored
markdown, *not* introspected from the `StrategyManifest` / `IndicatorManifest`
dataclasses — unlike `configuration/config_schema_guide.py`, which interpolates its
`RunConfig` field table from the model. Updating these tables when the manifest
contract changes is the normal cost of documentation, the same cost every documented
API pays; it is not architectural friction to be engineered away.

This refines ADR-0019: the config-schema guide can interpolate its table because a
`RunConfig` field maps cleanly to a row, but the component manifest tables cannot
without losing fidelity. Two columns have no faithful code source:

- **Type column encodes validation constraints, not annotations.** The guide states
  `owns_portfolio` is `Literal[false]` and `family` is `Literal["strategies"]`; the
  dataclass annotations are merely `bool` and the wider `ComponentFamily`. Introspecting
  the annotation would print a *less* accurate type than the curated cell.
- **Description column is authored domain semantics** ("must not be `.` or `..`", "no
  surrounding whitespace or control characters", the `example.ma_cross` examples) with
  no representation in `contracts.py`.

A mechanical "knowledge duplicated across modules" review (e.g. an automated architecture
pass) will read these tables as duplicating the dataclasses and propose introspecting
them. It should not — that trades curated, validation-accurate prose for a worse
rendering to avoid a maintenance step that was never the problem. This ADR exists so the
suggestion is not re-raised.

## Consequences

- `test_cli.py` pins the guides with *presence* assertions (the family literal,
  allocation outputs from code). That is the accepted guardrail.
- Residual risk accepted: the tables can go **stale** (a field added to a manifest
  dataclass is not auto-added to the guide). This is the ordinary stale-docs cost, caught
  at authoring/review time. We deliberately do **not** add a dataclass-completeness
  cross-check; the curated tables are the source of truth for *how to author*, the
  dataclasses for *what validates*, and the two are kept aligned by hand.

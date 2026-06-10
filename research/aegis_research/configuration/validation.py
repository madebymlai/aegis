"""Run Config validation — whole-tree coordinator.

With ``RunConfig`` as a whole-tree pydantic dataclass, one
``TypeAdapter(RunConfig).validate_python(raw)`` validates the entire tree
and accumulates all structural errors natively.

The coordinator owns:
- Top-level prepass: ``schema_version`` presence/version check,
  ``split.method`` inspection.
- Whole-tree pydantic ``validate_python`` call + error-to-issue adapter.
- Post-pydantic residual checks that need runtime state (registry membership,
  data-source whitelist, ranking-metric membership, lock coordinator rules).

Returns ``(RunConfig | None, list[ConfigValidationIssue])`` so the caller
can inspect whether pydantic construction succeeded while still seeing all
accumulated issues.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.configuration.field_types import IDENTIFIER_RE
from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    LOCK_ROLES,
    ConfigValidationIssue,
    DataConfig,
    Lock,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
)
from research.aegis_research.metrics import FrozenMetricRegistry

# Built once at import: TypeAdapter construction compiles the whole-tree core
# schema, which is too expensive to repeat per validation call.
_RUN_CONFIG_ADAPTER = TypeAdapter(RunConfig)


def validate_run_config(
    raw: dict[str, Any],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> tuple[RunConfig | None, list[ConfigValidationIssue]]:
    """Whole-tree run config validation with accumulated issues.

    Always returns the full issues list even when pydantic construction fails,
    so structural and registry errors are co-reported.
    """
    if not isinstance(raw, dict):
        return None, [ConfigValidationIssue("$", "run config must be a mapping")]

    issues: list[ConfigValidationIssue] = []

    # ── Prepass: tombstones, schema_version, removed fields, split method ──
    _prepass_raw_config(raw, issues)

    # ── Whole-tree pydantic validation ────────────────────────────────────
    config = None
    try:
        config = _RUN_CONFIG_ADAPTER.validate_python(raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues_whole_tree(e))

    # ── Post-pydantic checks (need runtime state) ─────────────────────────
    if config is not None:
        _post_validate_name(config.name, issues)
        _post_validate_data_source(config.data, issues)
        _post_validate_components(
            config.strategy, config.indicators, issues,
            component_registry=component_registry,
        )
        _post_validate_ranking_metric(config.ranking.metric, issues, registry=metric_registry)
        _check_lock_shape(config.lock, raw.get("lock"), issues)
    else:
        # Best-effort registry checks from raw so structural + registry
        # errors are co-reported.
        _best_effort_registry_checks(raw, issues, component_registry, metric_registry)

    return config, issues


# ── prepass ──────────────────────────────────────────────────────────────────

def _prepass_raw_config(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    """Raw-dict checks that must run before (or regardless of) pydantic validation.

    Removed legacy fields carry no tombstones: they fall through to
    ``extra="forbid"``'s unknown-key rejection like any field that never existed.
    """
    # schema_version presence + version check
    if "schema_version" not in raw or raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        issues.append(
            ConfigValidationIssue("schema_version", f"must be {CONFIG_SCHEMA_VERSION}")
        )

    # Optimization required (forward optimization contract)
    if "optimization" not in raw:
        issues.append(
            ConfigValidationIssue(
                "optimization", FORWARD_OPTIMIZATION_REQUIRED_MESSAGE
            )
        )

    # Split-method prepass (VBT introspection, produces dotted paths)
    optimization_raw = raw.get("optimization")
    if isinstance(optimization_raw, dict):
        split_raw = optimization_raw.get("split")
        if isinstance(split_raw, dict):
            from research.aegis_research.run_splits import validate_run_split_config

            validate_run_split_config(split_raw, issues, path="optimization.split")


# ── error adapter ────────────────────────────────────────────────────────────

def _validation_error_to_issues_whole_tree(
    error: ValidationError,
) -> list[ConfigValidationIssue]:
    """Map every pydantic ``ValidationError`` entry to a ``ConfigValidationIssue``.

    ``loc`` is a full-path tuple across the whole tree (e.g.
    ``('portfolio', 'gross_cap')`` or ``('indicators', 0, 'id')``).
    Int elements use bracket notation (``[i]``); string elements are dotted.
    The pydantic ``msg`` is taken verbatim.
    """
    issues: list[ConfigValidationIssue] = []
    for entry in error.errors():
        loc = entry["loc"]
        if not loc:
            path = "$"
        else:
            parts: list[str] = []
            for part in loc:
                if isinstance(part, int):
                    parts.append(f"[{part}]")
                else:
                    if parts:
                        parts.append(".")
                    parts.append(str(part))
            path = "".join(parts)
        issues.append(ConfigValidationIssue(path, entry["msg"]))
    return issues


# ── post-pydantic checks ────────────────────────────────────────────────────

def _post_validate_name(
    name: str,
    issues: list[ConfigValidationIssue],
) -> None:
    if not IDENTIFIER_RE.fullmatch(name) or name in {".", ".."}:
        issues.append(
            ConfigValidationIssue(
                "name",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )


def _post_validate_data_source(
    data: DataConfig,
    issues: list[ConfigValidationIssue],
) -> None:
    """Source whitelist (post-pydantic: needs runtime state)."""
    from research.aegis_research.market_data.sources import (
        LOCAL_DATA_SOURCES,
        remote_data_sources,
    )

    supported = LOCAL_DATA_SOURCES | remote_data_sources()
    if data.source not in supported:
        issues.append(
            ConfigValidationIssue(
                "data.source", f"must be one of {sorted(supported)}"
            )
        )


def _post_validate_components(
    strategy_config: RunSourceRefConfig,
    indicator_configs: list[RunIndicatorSourceConfig],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> None:
    """Component membership, output contract, and params checks."""
    strategy_def = _check_strategy_membership(
        strategy_config, issues, component_registry=component_registry
    )
    ind_defs = _check_indicators_membership(
        indicator_configs, issues, component_registry=component_registry
    )
    _check_component_output_contract(strategy_def, ind_defs, issues)
    if strategy_def is not None:
        _check_component_params("strategy", strategy_config, strategy_def, issues)
    for ind_path, ind_def in ind_defs:
        # Match by path rather than by positional zip — membership failures
        # can cause indicator_configs and ind_defs to be unaligned.
        for i, config in enumerate(indicator_configs):
            if ind_path == f"indicators[{i}]":
                _check_component_params(ind_path, config, ind_def, issues)
                break


def _check_strategy_membership(
    strategy_config: RunSourceRefConfig | None,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> ComponentDefinition | None:
    if strategy_config is None:
        return None
    if strategy_config.id == "all":
        issues.append(
            ConfigValidationIssue("strategy.id", "must select one component id")
        )
        return None
    try:
        return component_registry.get(
            ComponentSelection("strategies", strategy_config.id)
        )
    except ComponentRegistryError:
        issues.append(
            ConfigValidationIssue("strategy.id", "unknown strategy component id")
        )
        return None


def _check_indicators_membership(
    indicator_configs: list[RunIndicatorSourceConfig],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> list[tuple[str, ComponentDefinition]]:
    result: list[tuple[str, ComponentDefinition]] = []
    seen_ids: set[str] = set()
    for i, config in enumerate(indicator_configs):
        item_path = f"indicators[{i}]"
        # Duplicate indicator id detection (cross-item check — not expressible
        # as a pure pydantic field constraint on individual items).
        if config.id in seen_ids:
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.id",
                    f"duplicates indicator component id {config.id!r}",
                )
            )
        seen_ids.add(config.id)
        if config.id == "all":
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.id", "must select one component id"
                )
            )
            continue
        try:
            definition = component_registry.get(
                ComponentSelection("indicators", config.id)
            )
        except ComponentRegistryError:
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.id", "unknown indicator component id"
                )
            )
            continue
        result.append((item_path, definition))
    return result


def _check_component_output_contract(
    strategy_definition: ComponentDefinition | None,
    indicator_definitions: list[tuple[str, ComponentDefinition]],
    issues: list[ConfigValidationIssue],
) -> None:
    if strategy_definition is None:
        return
    produced: dict[str, str] = {}
    for path, definition in indicator_definitions:
        for output_name in getattr(definition.manifest, "output_names", ()):
            previous = produced.get(output_name)
            if previous is not None:
                issues.append(
                    ConfigValidationIssue(
                        f"{path}.id",
                        f"duplicates produced indicator output {output_name!r} from {previous}",
                    )
                )
                continue
            produced[output_name] = f"{path}.id"

    missing = sorted(
        set(getattr(strategy_definition.manifest, "consumes_outputs", ()))
        - set(produced)
    )
    if missing:
        issues.append(
            ConfigValidationIssue(
                "strategy.consumes_outputs",
                f"strategy consumes outputs not produced by configured indicators: {missing}",
            )
        )


def _check_component_params(
    path: str,
    config: RunSourceRefConfig | RunIndicatorSourceConfig | None,
    definition: ComponentDefinition | None,
    issues: list[ConfigValidationIssue],
) -> None:
    if config is None or definition is None:
        return
    param_names = tuple(getattr(definition.manifest, "param_names", ()))
    if not param_names and not config.params:
        return
    unknown = sorted(set(config.params) - set(param_names))
    if unknown:
        issues.append(
            ConfigValidationIssue(
                f"{path}.params",
                f"params must be declared by the component manifest; unknown: {unknown}",
            )
        )
        return
    if not param_names:
        return
    if getattr(definition.manifest, "param_space_callable", None):
        return
    provided = set(config.params)
    defaults = set(getattr(definition.manifest, "defaults", {}))
    missing = sorted(set(param_names) - provided - defaults)
    if missing:
        issues.append(
            ConfigValidationIssue(
                path,
                "must provide params, component defaults, or param_space_callable "
                f"for params {missing}",
            )
        )


def _post_validate_ranking_metric(
    metric: str,
    issues: list[ConfigValidationIssue],
    *,
    registry: FrozenMetricRegistry,
) -> None:
    if metric not in registry:
        issues.append(
            ConfigValidationIssue(
                "ranking.metric",
                f"must be one of {sorted(registry.ids())}",
            )
        )


def _check_lock_shape(
    lock: Lock | None,
    lock_raw: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    """Typo-catcher: reject empty run_id and unknown role keywords."""
    if lock is None:
        return
    was_handle = isinstance(lock_raw, str)
    if not lock.run_id:
        issues.append(ConfigValidationIssue("lock", "run_id must not be empty"))
    if was_handle and lock.candidate_id not in LOCK_ROLES:
        _lock_roles_label = ", ".join(LOCK_ROLES)
        issues.append(
            ConfigValidationIssue(
                "lock",
                f"role must be one of: {_lock_roles_label} (got {lock.candidate_id!r})",
            )
        )


# ── best-effort registry checks from raw (when pydantic validation failed) ──

def _best_effort_registry_checks(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> None:
    """Co-report registry errors even when pydantic structural validation failed."""
    # Strategy
    strategy_raw = raw.get("strategy")
    if isinstance(strategy_raw, dict) and "id" in strategy_raw:
        sid = strategy_raw.get("id")
        if sid == "all":
            issues.append(
                ConfigValidationIssue("strategy.id", "must select one component id")
            )
        elif isinstance(sid, str) and sid:
            try:
                component_registry.get(ComponentSelection("strategies", sid))
            except ComponentRegistryError:
                issues.append(
                    ConfigValidationIssue("strategy.id", "unknown strategy component id")
                )

    # Indicators
    indicators_raw = raw.get("indicators")
    if isinstance(indicators_raw, list):
        seen: set[str] = set()
        for i, item in enumerate(indicators_raw):
            if not isinstance(item, dict):
                continue
            iid = item.get("id")
            if not isinstance(iid, str) or not iid:
                continue
            if iid in seen:
                issues.append(
                    ConfigValidationIssue(
                        f"indicators[{i}].id",
                        f"duplicates indicator component id {iid!r}",
                    )
                )
                continue
            seen.add(iid)
            if iid == "all":
                issues.append(
                    ConfigValidationIssue(
                        f"indicators[{i}].id", "must select one component id"
                    )
                )
                continue
            try:
                component_registry.get(ComponentSelection("indicators", iid))
            except ComponentRegistryError:
                issues.append(
                    ConfigValidationIssue(
                        f"indicators[{i}].id", "unknown indicator component id"
                    )
                )

    # Ranking metric
    ranking_raw = raw.get("ranking")
    if isinstance(ranking_raw, dict):
        metric = ranking_raw.get("metric")
        if isinstance(metric, str) and metric and metric not in metric_registry:
            issues.append(
                ConfigValidationIssue(
                    "ranking.metric",
                    f"must be one of {sorted(metric_registry.ids())}",
                )
            )




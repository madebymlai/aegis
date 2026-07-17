"""Registry cross-checks that verify Run Config component/metric selections.

One public entry: ``cross_check_registries`` dispatches to full checks
(validated ``RunConfig``) or best-effort membership checks (raw dict when
pydantic structural validation failed).  Package-internal — not part of the
public config surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from research.aegis_research.configuration.schema import (
    ConfigValidationIssue,
    RunConfig,
)
from research.aegis_research.metrics import FrozenMetricRegistry

if TYPE_CHECKING:
    from research.aegis_research.component_registry import (
        ComponentDefinition,
        FrozenComponentRegistry,
    )


def cross_check_registries(
    config_or_raw: RunConfig | dict[str, Any],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> list[ConfigValidationIssue]:
    """Registry cross-checks — query, not accumulator-mutation.

    Returns a fresh issue list.  The caller extends its own issue list.
    """
    if isinstance(config_or_raw, RunConfig):
        return _full_cross_checks(
            config_or_raw,
            component_registry=component_registry,
            metric_registry=metric_registry,
        )
    return _raw_best_effort_checks(
        config_or_raw,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )


# ── full dialect (validated RunConfig) ────────────────────────────────────────


def _full_cross_checks(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> list[ConfigValidationIssue]:
    issues: list[ConfigValidationIssue] = []

    strategy_def = _check_strategy_membership(
        config.strategy, issues, component_registry=component_registry
    )
    ind_defs = _check_indicators_membership(
        config.indicators, issues, component_registry=component_registry
    )
    _check_output_contract(strategy_def, ind_defs, issues)
    if strategy_def is not None:
        _check_params("strategy", config.strategy, strategy_def, issues)
    for i, ind_def in ind_defs:
        _check_params(f"indicators[{i}]", config.indicators[i], ind_def, issues)

    _check_metric_membership(
        config.ranking.metric, issues, metric_registry=metric_registry
    )
    for i, metric in enumerate(config.report.metrics):
        _check_metric_membership(
            metric, issues, metric_registry=metric_registry, path=f"report.metrics[{i}]"
        )

    return issues


def _check_strategy_membership(
    strategy_config: object,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> ComponentDefinition | None:
    from research.aegis_research.configuration.schema import RunSourceRefConfig

    if not isinstance(strategy_config, RunSourceRefConfig):
        return None
    if strategy_config.id == "all":
        issues.append(
            ConfigValidationIssue("strategy.id", "must select one component id")
        )
        return None
    from research.aegis_research.component_registry import (
        ComponentRegistryError,
        ComponentSelection,
    )

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
    indicator_configs: object,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> list[tuple[int, ComponentDefinition]]:
    from research.aegis_research.configuration.schema import RunIndicatorSourceConfig

    if not isinstance(indicator_configs, list):
        return []

    result: list[tuple[int, ComponentDefinition]] = []
    seen_ids: set[str] = set()
    from research.aegis_research.component_registry import (
        ComponentRegistryError,
        ComponentSelection,
    )

    for i, config in enumerate(indicator_configs):
        if not isinstance(config, RunIndicatorSourceConfig):
            continue
        item_path = f"indicators[{i}]"
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
        result.append((i, definition))
    return result


def _check_output_contract(
    strategy_definition: ComponentDefinition | None,
    indicator_definitions: list[tuple[int, ComponentDefinition]],
    issues: list[ConfigValidationIssue],
) -> None:
    if strategy_definition is None:
        return
    produced: dict[str, str] = {}
    for i, definition in indicator_definitions:
        path = f"indicators[{i}]"
        for output_name in definition.produced_output_names():
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

    missing = sorted(set(strategy_definition.consumed_output_names()) - set(produced))
    if missing:
        issues.append(
            ConfigValidationIssue(
                "strategy.consumes_outputs",
                f"strategy consumes outputs not produced by configured indicators: {missing}",
            )
        )


def _check_params(
    path: str,
    config: object,
    definition: ComponentDefinition | None,
    issues: list[ConfigValidationIssue],
) -> None:
    from research.aegis_research.configuration.schema import (
        RunIndicatorSourceConfig,
        RunSourceRefConfig,
    )

    if not isinstance(config, (RunSourceRefConfig, RunIndicatorSourceConfig)):
        return
    if definition is None:
        return

    provided = frozenset(config.params)
    unknown = sorted(definition.undeclared_params(provided))
    if unknown:
        issues.append(
            ConfigValidationIssue(
                f"{path}.params",
                f"params must be declared by the component manifest; unknown: {unknown}",
            )
        )
        return

    missing = sorted(definition.unsatisfied_params(provided))
    if missing:
        issues.append(
            ConfigValidationIssue(
                path,
                "must provide params, component defaults, or module-level param_space "
                f"for params {missing}",
            )
        )


def _check_metric_membership(
    metric: str,
    issues: list[ConfigValidationIssue],
    *,
    metric_registry: FrozenMetricRegistry,
    path: str = "ranking.metric",
) -> None:
    if metric not in metric_registry:
        issues.append(
            ConfigValidationIssue(
                path,
                f"must be one of {sorted(metric_registry.ids())}",
            )
        )


# ── raw best-effort dialect ─────────────────────────────────────────────────


def _raw_best_effort_checks(
    raw: dict[str, Any],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> list[ConfigValidationIssue]:
    """Best-effort registry checks from raw dict.

    When pydantic structural validation failed (no typed RunConfig), we best-effort
    check membership from the raw dict so structural + registry errors are
    co-reported.  Only membership checks are performed — params, output contract,
    and lock shape checks need typed data and are skipped.
    """
    issues: list[ConfigValidationIssue] = []

    from research.aegis_research.component_registry import (
        ComponentRegistryError,
        ComponentSelection,
    )

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

    return issues

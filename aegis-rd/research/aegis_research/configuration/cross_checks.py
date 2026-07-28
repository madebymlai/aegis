"""Typed registry cross-checks for Run Config component/metric selections."""

from __future__ import annotations

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.configuration.schema import (
    ConfigValidationIssue,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
)
from research.aegis_research.metrics import FrozenMetricRegistry


def cross_check_registries(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> list[ConfigValidationIssue]:
    """Registry cross-checks — query, not accumulator-mutation.

    Returns a fresh issue list.  The caller extends its own issue list.
    """
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

    _check_metric_membership(config.ranking.metric, issues, metric_registry=metric_registry)
    for i, metric in enumerate(config.report.metrics):
        _check_metric_membership(
            metric, issues, metric_registry=metric_registry, path=f"report.metrics[{i}]"
        )

    return issues


def _check_strategy_membership(
    strategy_config: RunSourceRefConfig,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> ComponentDefinition | None:
    if strategy_config.id == "all":
        issues.append(ConfigValidationIssue("strategy.id", "must select one component id"))
        return None
    try:
        return component_registry.get(ComponentSelection("strategies", strategy_config.id))
    except ComponentRegistryError:
        issues.append(ConfigValidationIssue("strategy.id", "unknown strategy component id"))
        return None


def _check_indicators_membership(
    indicator_configs: list[RunIndicatorSourceConfig],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> list[tuple[int, ComponentDefinition]]:
    result: list[tuple[int, ComponentDefinition]] = []
    seen_ids: set[str] = set()
    for i, config in enumerate(indicator_configs):
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
            issues.append(ConfigValidationIssue(f"{item_path}.id", "must select one component id"))
            continue
        try:
            definition = component_registry.get(ComponentSelection("indicators", config.id))
        except ComponentRegistryError:
            issues.append(
                ConfigValidationIssue(f"{item_path}.id", "unknown indicator component id")
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
    config: RunSourceRefConfig | RunIndicatorSourceConfig,
    definition: ComponentDefinition,
    issues: list[ConfigValidationIssue],
) -> None:
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

"""Component and Indicator reference validation.

Validates ``strategy`` and ``indicators`` refs against the frozen Component registry:
component ids must resolve, ``params:`` must be values-only and manifest-declared (or
sourced from defaults), and the strategy's consumed outputs must be produced by the
configured indicators. Whole-Candidate reproduction lives on the top-level ``lock:`` —
there is no per-Component lock/candidate reference surface (ADR-0006).
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.configuration.schema import (
    EXPERIMENT_NAME_RE,
    ConfigValidationIssue,
)
from research.aegis_research.configuration.validation.base import (
    _require_str,
    _validate_json_like,
    _validate_known_keys,
)


def _validate_component_indicator_refs(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> tuple[tuple[str, ComponentDefinition], ...]:
    if isinstance(value, dict) and "specs" in value:
        issues.append(
            ConfigValidationIssue(
                path,
                "must use component refs; legacy indicators.specs is not accepted in run configs",
            )
        )
        return ()
    if not isinstance(value, list):
        issues.append(ConfigValidationIssue(path, "must be a list"))
        return ()

    seen: dict[str, str] = {}
    definitions: list[tuple[str, ComponentDefinition]] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        definition = _validate_component_ref(
            item_path,
            item,
            "indicators",
            issues,
            component_registry=component_registry,
        )
        if definition is None:
            continue
        previous = seen.get(definition.id)
        if previous is not None:
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.id",
                    f"duplicates indicator component id {definition.id!r} from {previous}",
                )
            )
            continue
        seen[definition.id] = f"{item_path}.id"
        definitions.append((item_path, definition))
    return tuple(definitions)


def _validate_component_ref(
    path: str,
    value: Any,
    family: str,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> ComponentDefinition | None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return None
    allowed = {"id", "params"}
    _validate_known_keys(path, value, allowed, issues)
    if not _require_str(f"{path}.id", value, issues):
        return None
    component_id = value["id"]
    if component_id == "all":
        issues.append(ConfigValidationIssue(f"{path}.id", "must select one component id"))
        return None
    if not EXPERIMENT_NAME_RE.fullmatch(component_id):
        issues.append(
            ConfigValidationIssue(
                f"{path}.id",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )
        return None

    try:
        definition = component_registry.get(ComponentSelection(family, component_id))
    except ComponentRegistryError:
        singular = family[:-1] if family.endswith("s") else family
        issues.append(ConfigValidationIssue(f"{path}.id", f"unknown {singular} component id"))
        return None

    params = _validate_component_params(
        f"{path}.params",
        value.get("params", {}),
        tuple(getattr(definition.manifest, "param_names", ())),
        issues,
        explicit="params" in value,
    )
    _validate_component_param_sources(path, value, definition, params, issues)
    return definition


def _validate_component_params(
    path: str,
    value: Any,
    param_names: tuple[str, ...],
    issues: list[ConfigValidationIssue],
    *,
    explicit: bool,
) -> dict[str, Any] | None:
    if not explicit:
        return {}
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return None
    _validate_json_like(path, value, issues)
    unknown = sorted(set(value) - set(param_names))
    if unknown:
        issues.append(
            ConfigValidationIssue(
                path,
                f"params must be declared by the component manifest; unknown: {unknown}",
            )
        )
    return dict(value)


def _validate_component_param_sources(
    path: str,
    value: dict[str, Any],
    definition: ComponentDefinition,
    params: dict[str, Any] | None,
    issues: list[ConfigValidationIssue],
) -> None:
    param_names = tuple(getattr(definition.manifest, "param_names", ()))
    if not param_names:
        return
    if getattr(definition.manifest, "param_space_callable", None):
        return
    provided = set(params or {})
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


def _validate_component_output_contract(
    strategy_definition: ComponentDefinition | None,
    indicator_definitions: tuple[tuple[str, ComponentDefinition], ...],
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
        set(getattr(strategy_definition.manifest, "consumes_outputs", ())) - set(produced)
    )
    if missing:
        issues.append(
            ConfigValidationIssue(
                "strategy.consumes_outputs",
                f"strategy consumes outputs not produced by configured indicators: {missing}",
            )
        )

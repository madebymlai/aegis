"""Run Config validation — domain-dispatching coordinator.

This package validates a raw Run Config mapping into a list of ``ConfigValidationIssue``.
The coordinator owns the top-level Run shape (schema version, name, output dir, removed
legacy fields) and sequences the domain validators; each domain lives in its own module
and imports only what it validates:

- ``base``         — shared type/structure validators
- ``components``   — strategy & indicator component refs and output contracts
- ``data``         — market-data source, arrays, quality policy, paths
- ``optimization`` — search policy, run split, random policy, execute passthrough
- ``metrics``      — ranking metric selection

Portfolio and report are pydantic-ported — validated by the coordinator in
``resolution._build_resolved_run_config`` via ``TypeAdapter`` + ``ValidationError``
adapter, with a tombstone prepass for removed fields.

The public surface (re-exported below) is the validation entry point plus the two
validators reached directly by callers outside this package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.component_registry import FrozenComponentRegistry
from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    EXPERIMENT_NAME_RE,
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    ConfigValidationIssue,
    DataConfig,
)
from research.aegis_research.configuration.validation.base import (
    _optional_str,
    _require_int,
    _require_str,
    _section,
    _validate_known_keys,
)
from research.aegis_research.configuration.validation.components import (
    _validate_component_indicator_refs,
    _validate_component_output_contract,
    _validate_component_ref,
)
from research.aegis_research.configuration.validation.data import (
    _is_absolute_or_user_path,
    _validate_data,
)
from research.aegis_research.configuration.validation.lock import _validate_lock
from research.aegis_research.configuration.validation.metrics import _validate_ranking
from research.aegis_research.metrics import FrozenMetricRegistry

__all__ = [
    "_is_absolute_or_user_path",
    "_validate_ranking",
    "_validate_raw_run_config",
]


def _validate_raw_run_config(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> None:
    _validate_known_keys("$", raw, _run_allowed_top_level_keys(), issues)
    _require_int("schema_version", raw, issues, positive=True)
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        issues.append(ConfigValidationIssue("schema_version", f"must be {CONFIG_SCHEMA_VERSION}"))
    _validate_removed_training_fields(raw, issues)
    if _require_str("name", raw, issues):
        _validate_experiment_name(raw["name"], issues)
    _validate_output_dir(raw, issues)

    # Portfolio and report sections are pydantic-ported, validated upstream
    # in the coordinator (resolution._build_resolved_run_config).
    data = _section(raw, "data", set(DataConfig.__dataclass_fields__), issues)
    _validate_data(data, issues, validate_paths=True)
    _validate_lock(raw, issues)
    _validate_run_config(
        raw,
        issues,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )


def _run_allowed_top_level_keys() -> set[str]:
    return {
        "schema_version",
        "name",
        "data",
        "portfolio",
        "report",
        "output_dir",
        "optimization",
        "lock",
        "indicators",
        "ranking",
        "strategy",
    }


def _validate_run_config(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> None:
    strategy_definition = _validate_component_ref(
        "strategy",
        raw.get("strategy"),
        "strategies",
        issues,
        component_registry=component_registry,
    )
    indicator_definitions = _validate_component_indicator_refs(
        "indicators",
        raw.get("indicators"),
        issues,
        component_registry=component_registry,
    )
    _validate_component_output_contract(strategy_definition, indicator_definitions, issues)
    _validate_ranking("ranking", raw.get("ranking"), issues, registry=metric_registry)
    if "optimization" not in raw:
        issues.append(
            ConfigValidationIssue(
                "optimization",
                FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
            )
        )


def _validate_removed_training_fields(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    for key in ("lane", "train", "model", "labels", "label", "labeler", "signals"):
        if key in raw:
            issues.append(
                ConfigValidationIssue(
                    key,
                    "training and lane fields are not supported by the single run config contract",
                )
            )


def _validate_experiment_name(value: str, issues: list[ConfigValidationIssue]) -> None:
    if not EXPERIMENT_NAME_RE.fullmatch(value) or value in {".", ".."}:
        issues.append(
            ConfigValidationIssue(
                "name",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )


def _validate_output_dir(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    if not _optional_str("output_dir", raw, issues):
        return
    output_dir = raw.get("output_dir")
    if output_dir is None:
        return
    path = Path(str(output_dir))
    if path.is_absolute() or ".." in path.parts:
        issues.append(
            ConfigValidationIssue("output_dir", "must be a relative path under the project root")
        )
        return
    current = Path.cwd()
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            issues.append(
                ConfigValidationIssue("output_dir", "must not contain symlinked path components")
            )
            return
    project_root = Path.cwd().resolve(strict=False)
    resolved = (Path.cwd() / path).resolve(strict=False)
    if resolved != project_root and project_root not in resolved.parents:
        issues.append(ConfigValidationIssue("output_dir", "must resolve under the project root"))
        return

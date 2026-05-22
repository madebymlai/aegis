from __future__ import annotations

import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pandas as pd

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    DATA_ARRAY_SHORTCUTS,
    DATA_QUALITY_DEGRADATIONS,
    DENIED_PASSTHROUGH_KEYS,
    EXPERIMENT_NAME_RE,
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    MISSING_POLICIES,
    OPTIMIZATION_RETURN_GRID_POLICIES,
    OPTIMIZATION_SEARCH_POLICIES,
    PORTFOLIO_DIRECTIONS,
    PORTFOLIO_TARGET_SIZE_TYPES,
    RANKING_DIRECTIONS,
    RUN_EXECUTABLE_DENIED_KEYS,
    ConfigValidationIssue,
    DataConfig,
    DataQualityConfig,
    OptimizationConfig,
    OptimizationEvidenceConfig,
    PortfolioConfig,
    ReportConfig,
    RunSplitConfig,
    has_data_array_token_shape,
)
from research.aegis_research.configuration.secrets import _validate_no_inline_secrets
from research.aegis_research.market_data.sources import LOCAL_DATA_SOURCES, remote_data_sources
from research.aegis_research.metrics import FrozenMetricRegistry
from research.aegis_research.run_splits import validate_run_split_config


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

    data = _section(raw, "data", set(DataConfig.__dataclass_fields__), issues)
    portfolio = _section(
        raw,
        "portfolio",
        set(PortfolioConfig.__dataclass_fields__) | {"size", "size_type"},
        issues,
    )
    report = _section(raw, "report", set(ReportConfig.__dataclass_fields__), issues)
    _validate_data(data, issues, validate_paths=True)
    _validate_portfolio(portfolio, issues)
    _validate_report(report, issues)
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
    _validate_optimization(raw, issues)
def _validate_run_split(
    split: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    path: str = "split",
) -> None:
    _optional_int(f"{path}.max_splits", split, issues, positive=True)
    _optional_int(f"{path}.max_estimated_output_cells", split, issues, positive=True)
    _optional_int(f"{path}.max_public_artifact_bytes", split, issues, positive=True)

    params = split.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue(f"{path}.params", "must be a mapping"))
    else:
        _validate_json_like(f"{path}.params", params, issues)
        _validate_no_inline_secrets(f"{path}.params", params, issues)
        _validate_no_run_executable_keys(f"{path}.params", params, issues)
        if "set_labels" in params:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.params.set_labels",
                    "set roles are owned by Aegis and assigned positionally "
                    "(set 0 selection, set 1 held_out); set_labels is not configurable",
                )
            )
    validate_run_split_config(split, issues, path=path)


def _validate_optimization(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    if "optimization" not in raw:
        return
    optimization = raw.get("optimization")
    if not isinstance(optimization, dict):
        issues.append(ConfigValidationIssue("optimization", "must be a mapping"))
        return

    _validate_known_keys(
        "optimization",
        optimization,
        set(OptimizationConfig.__dataclass_fields__),
        issues,
    )
    if _require_str("optimization.search", optimization, issues):
        search = optimization["search"]
        if search not in OPTIMIZATION_SEARCH_POLICIES:
            issues.append(
                ConfigValidationIssue(
                    "optimization.search",
                    f"must be one of {sorted(OPTIMIZATION_SEARCH_POLICIES)}",
                )
            )
    else:
        search = None

    _validate_optimization_split(optimization, issues)
    _validate_optimization_random_policy(optimization, issues, search=search)
    _optional_int("optimization.seed", optimization, issues, minimum=0, allow_none=True)
    _validate_optimization_execute(optimization.get("execute", {}), issues)
    _validate_optimization_evidence(optimization.get("evidence", {}), issues)


def _validate_optimization_split(
    optimization: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    if "split" not in optimization:
        issues.append(ConfigValidationIssue("optimization.split", "is required for optimization"))
        return
    split = optimization["split"]
    if not isinstance(split, dict):
        issues.append(ConfigValidationIssue("optimization.split", "must be a mapping"))
        return
    _validate_known_keys(
        "optimization.split",
        split,
        set(RunSplitConfig.__dataclass_fields__),
        issues,
    )
    _validate_run_split(split, issues, path="optimization.split")


def _validate_optimization_random_policy(
    optimization: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    search: str | None,
) -> None:
    random_subset = optimization.get("random_subset")
    if "random_subset" in optimization:
        _optional_int(
            "optimization.random_subset",
            optimization,
            issues,
            positive=True,
            allow_none=True,
        )
    if search == "random" and random_subset is None:
        issues.append(
            ConfigValidationIssue(
                "optimization.random_subset",
                "is required when optimization.search is 'random'",
            )
        )
    if search == "random" and optimization.get("seed") is None:
        issues.append(
            ConfigValidationIssue(
                "optimization.seed",
                "is required when optimization.search is 'random' so sampled evidence is deterministic",
            )
        )
    if search == "grid" and random_subset is not None:
        issues.append(
            ConfigValidationIssue(
                "optimization.random_subset",
                "only valid when optimization.search is 'random'",
            )
        )


OPTIMIZATION_EXECUTE_RESERVED_KEYS = frozenset(
    {
        "random_subset",
        "seed",
        "merge_func",
        "raise_no_results",
        "filter_results",
        "selection",
        "return_grid",
    }
)


def _validate_optimization_execute(value: Any, issues: list[ConfigValidationIssue]) -> None:
    path = "optimization.execute"
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_json_like(path, value, issues)
    _validate_no_inline_secrets(path, value, issues)
    _validate_no_run_executable_keys(path, value, issues)
    reserved = sorted(set(value) & OPTIMIZATION_EXECUTE_RESERVED_KEYS)
    if reserved:
        issues.append(
            ConfigValidationIssue(
                path,
                f"reserved keys {reserved} are owned by optimization.search / "
                "optimization.evidence / Aegis ranking policy and must not appear "
                "under optimization.execute",
            )
        )


def _validate_optimization_evidence(value: Any, issues: list[ConfigValidationIssue]) -> None:
    path = "optimization.evidence"
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, set(OptimizationEvidenceConfig.__dataclass_fields__), issues)
    _validate_json_like(path, value, issues)
    _validate_no_inline_secrets(path, value, issues)
    if "return_grid" in value:
        return_grid = value["return_grid"]
        if not isinstance(return_grid, str) or return_grid not in OPTIMIZATION_RETURN_GRID_POLICIES:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.return_grid",
                    f"must be one of {sorted(OPTIMIZATION_RETURN_GRID_POLICIES)}",
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
    allowed = {"id", "lock_id", "candidate_id", "run_id", "params"}
    _validate_known_keys(path, value, allowed, issues)
    _validate_no_run_executable_keys(path, value, issues)
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
    _optional_str(f"{path}.lock_id", value, issues, allow_none=True)
    _optional_str(f"{path}.candidate_id", value, issues, allow_none=True)
    _optional_str(f"{path}.run_id", value, issues, allow_none=True)
    if value.get("lock_id") is not None and value.get("candidate_id") is not None:
        issues.append(
            ConfigValidationIssue(
                path,
                "lock_id and candidate_id are mutually exclusive",
            )
        )
    if value.get("candidate_id") is not None and value.get("run_id") is None:
        issues.append(
            ConfigValidationIssue(
                f"{path}.run_id",
                "is required when candidate_id is set",
            )
        )
    if value.get("run_id") is not None and value.get("candidate_id") is None:
        issues.append(
            ConfigValidationIssue(
                f"{path}.run_id",
                "is only valid when candidate_id is set",
            )
        )

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
    _validate_no_inline_secrets(path, value, issues)
    _validate_no_run_executable_keys(path, value, issues)
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
    if value.get("lock_id") is not None or value.get("candidate_id") is not None:
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
                "must provide params, component defaults, lock_id, candidate_id, or "
                f"param_space_callable for params {missing}",
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

    missing = sorted(set(getattr(strategy_definition.manifest, "consumes_outputs", ())) - set(produced))
    if missing:
        issues.append(
            ConfigValidationIssue(
                "strategy.consumes_outputs",
                f"strategy consumes outputs not produced by configured indicators: {missing}",
            )
        )


def _validate_ranking(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    registry: FrozenMetricRegistry,
) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, {"metric", "direction", "secondary_metrics", "rank_by"}, issues)
    metric = value.get("metric")
    if not isinstance(metric, str) or not metric:
        issues.append(ConfigValidationIssue(f"{path}.metric", "must be a non-empty string"))
    else:
        _validate_metric_selection(
            f"{path}.metric",
            metric,
            issues,
            registry=registry,
            require_primary=True,
        )
    direction = value.get("direction")
    if not isinstance(direction, str) or direction not in RANKING_DIRECTIONS:
        issues.append(
            ConfigValidationIssue(
                f"{path}.direction", f"must be one of {sorted(RANKING_DIRECTIONS)}"
            )
        )
    if "rank_by" in value:
        issues.append(
            ConfigValidationIssue(
                f"{path}.rank_by",
                "was removed; include 'baseline_delta' in secondary_metrics for baseline comparison",
            )
        )
    _validate_secondary_metrics(
        path,
        value.get("secondary_metrics", []),
        issues,
        primary_metric=metric if isinstance(metric, str) else None,
        registry=registry,
    )


def _validate_secondary_metrics(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    primary_metric: str | None,
    registry: FrozenMetricRegistry,
) -> None:
    if not isinstance(value, list):
        issues.append(ConfigValidationIssue(f"{path}.secondary_metrics", "must be a list"))
        return
    seen: set[str] = set()
    for index, metric_id in enumerate(value):
        item_path = f"{path}.secondary_metrics[{index}]"
        if not isinstance(metric_id, str) or not metric_id:
            issues.append(ConfigValidationIssue(item_path, "must be a non-empty metric id string"))
            continue
        if metric_id == primary_metric:
            issues.append(ConfigValidationIssue(item_path, "must not repeat primary metric"))
            continue
        if metric_id in seen:
            issues.append(ConfigValidationIssue(item_path, "duplicate secondary metric"))
            continue
        seen.add(metric_id)
        _validate_metric_selection(
            item_path,
            metric_id,
            issues,
            registry=registry,
            require_primary=False,
        )


def _validate_metric_selection(
    path: str,
    metric_id: str,
    issues: list[ConfigValidationIssue],
    *,
    registry: FrozenMetricRegistry,
    require_primary: bool,
) -> None:
    if metric_id not in registry:
        issues.append(ConfigValidationIssue(path, f"must be one of {sorted(registry.ids())}"))
        return
    definition = registry.get(metric_id)
    if require_primary and not definition.primary_eligible:
        issues.append(ConfigValidationIssue(path, f"metric {metric_id!r} is not primary-eligible"))
    if not require_primary and not definition.secondary_eligible:
        issues.append(ConfigValidationIssue(path, f"metric {metric_id!r} is not secondary-eligible"))


def _validate_no_run_executable_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in RUN_EXECUTABLE_DENIED_KEYS:
                issues.append(
                    ConfigValidationIssue(
                        child_path,
                        "is not allowed in run config; select trusted component IDs",
                    )
                )
            _validate_no_run_executable_keys(child_path, item, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_run_executable_keys(f"{path}[{index}]", item, issues)


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


def _validate_data(
    data: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    validate_paths: bool = False,
) -> None:
    source = data.get("source", "synthetic")
    if not _optional_str("data.source", data, issues):
        return
    source = str(source)
    supported_remote_sources = remote_data_sources()
    supported_sources = LOCAL_DATA_SOURCES | supported_remote_sources
    if source not in supported_sources:
        issues.append(
            ConfigValidationIssue("data.source", f"must be one of {sorted(supported_sources)}")
        )

    if "symbols" in data:
        _require_str_list("data.symbols", data["symbols"], issues, non_empty=True)
    if source in supported_remote_sources and "symbols" not in data:
        issues.append(ConfigValidationIssue("data.symbols", "is required for remote data sources"))

    _optional_str("data.start", data, issues, allow_none=True)
    _optional_str("data.end", data, issues, allow_none=True)
    _optional_str("data.timeframe", data, issues)
    _optional_str("data.path", data, issues, allow_none=True)
    _optional_int("data.seed", data, issues)
    _optional_int("data.rows", data, issues, positive=True)

    if source == "csv" and not data.get("path"):
        issues.append(ConfigValidationIssue("data.path", "is required for csv source"))
    elif source == "csv" and validate_paths:
        _validate_relative_project_path("data.path", data.get("path"), issues)
    if source in supported_remote_sources:
        for key in ("start", "end", "timeframe"):
            if not data.get(key):
                issues.append(
                    ConfigValidationIssue(f"data.{key}", f"is required for {source} source")
                )

    _optional_enum("data.missing_index", data, MISSING_POLICIES, issues)
    _optional_enum("data.missing_columns", data, MISSING_POLICIES, issues)
    _optional_str_bool_none("data.tz_localize", data, issues)
    _optional_str_bool_none("data.tz_convert", data, issues)
    _optional_bool("data.skip_on_error", data, issues)
    _optional_bool("data.silence_warnings", data, issues)
    _validate_data_arrays(data, issues)
    _validate_quality_policy(data.get("quality", {}), issues)
    _validate_passthrough("data.wrapper_kwargs", data.get("wrapper_kwargs", {}), issues)
    _validate_passthrough("data.provider_kwargs", data.get("provider_kwargs", {}), issues)
    _validate_passthrough("data.execution_kwargs", data.get("execution_kwargs", {}), issues)

    if source in LOCAL_DATA_SOURCES:
        for key in ("wrapper_kwargs", "provider_kwargs", "execution_kwargs"):
            if data.get(key):
                issues.append(
                    ConfigValidationIssue(f"data.{key}", f"is not supported for {source} source")
                )
    if data.get("skip_on_error") and "skipped_symbols" not in _quality_degradations(data):
        issues.append(
            ConfigValidationIssue(
                "data.skip_on_error",
                "requires data.quality.allowed_degradations to include 'skipped_symbols'",
            )
        )


def _validate_relative_project_path(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if not isinstance(value, str) or not value:
        return
    parts = (
        set(Path(value).parts) | set(PurePosixPath(value).parts) | set(PureWindowsPath(value).parts)
    )
    if _is_absolute_or_user_path(value) or ".." in parts:
        issues.append(ConfigValidationIssue(path, "must be a relative path under the project root"))


def _is_absolute_or_user_path(value: str) -> bool:
    if value.startswith("~"):
        return True
    try:
        return (
            Path(value).is_absolute()
            or PurePosixPath(value).is_absolute()
            or PureWindowsPath(value).is_absolute()
        )
    except ValueError:
        return False


def _validate_data_arrays(data: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    path = "data.arrays"
    if "arrays" not in data:
        issues.append(ConfigValidationIssue(path, "is required"))
        return
    value = data["arrays"]
    if not isinstance(value, list):
        issues.append(ConfigValidationIssue(path, "must be a non-empty list of VBT feature names"))
        return
    if not value:
        issues.append(ConfigValidationIssue(path, "must not be empty"))
        return
    for index, item in enumerate(value):
        _validate_data_array_token(f"{path}[{index}]", item, issues)


def _validate_data_array_token(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if not isinstance(value, str) or not value:
        issues.append(ConfigValidationIssue(path, "must be a non-empty string"))
        return
    if value in DATA_ARRAY_SHORTCUTS:
        return
    if not has_data_array_token_shape(value):
        issues.append(
            ConfigValidationIssue(
                path,
                "must be a VBT feature name without surrounding whitespace or control characters",
            )
        )


def _validate_quality_policy(value: Any, issues: list[ConfigValidationIssue]) -> None:
    path = "data.quality"
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, set(DataQualityConfig.__dataclass_fields__), issues)
    if "allowed_degradations" in value:
        degradations = value["allowed_degradations"]
        if not isinstance(degradations, list) or not all(
            isinstance(item, str) for item in degradations
        ):
            issues.append(
                ConfigValidationIssue(
                    "data.quality.allowed_degradations",
                    "must be a list of strings",
                )
            )
            return
        for index, degradation in enumerate(degradations):
            if degradation not in DATA_QUALITY_DEGRADATIONS:
                issues.append(
                    ConfigValidationIssue(
                        f"data.quality.allowed_degradations[{index}]",
                        f"must be one of {sorted(DATA_QUALITY_DEGRADATIONS)}",
                    )
                )


def _quality_degradations(data: dict[str, Any]) -> set[str]:
    quality = data.get("quality", {})
    if not isinstance(quality, dict):
        return set()
    degradations = quality.get("allowed_degradations", [])
    if not isinstance(degradations, list):
        return set()
    return {str(item) for item in degradations}


def _validate_portfolio(portfolio: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_number("portfolio.init_cash", portfolio, issues, positive=True)
    _optional_number("portfolio.fees", portfolio, issues, minimum=0)
    _optional_number("portfolio.slippage", portfolio, issues, minimum=0)
    if "entry_budget" not in portfolio:
        issues.append(ConfigValidationIssue("portfolio.entry_budget", "is required"))
    else:
        _optional_number("portfolio.entry_budget", portfolio, issues, positive=True, maximum=1)
    if "size" in portfolio:
        issues.append(
            ConfigValidationIssue(
                "portfolio.size",
                "was removed; use portfolio.entry_budget for v1 signal entry sizing",
            )
        )
    if "size_type" in portfolio and not isinstance(portfolio["size_type"], str):
        issues.append(ConfigValidationIssue("portfolio.size_type", "must be a string"))
    elif "size_type" in portfolio:
        if portfolio["size_type"] in PORTFOLIO_TARGET_SIZE_TYPES:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    "target allocation sizing is deferred; baseline signal simulation uses portfolio.entry_budget",
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    "was removed; baseline signal simulation resolves valuepercent sizing internally",
                )
            )
    direction = portfolio.get("direction", "longonly")
    if "direction" in portfolio and not isinstance(direction, str):
        issues.append(ConfigValidationIssue("portfolio.direction", "must be a string"))
    elif direction != "longonly":
        if direction in {"both", "shortonly"}:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.direction",
                    "v1 strategy signal contract is long-only; use longonly",
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.direction",
                    f"must be one of {sorted(PORTFOLIO_DIRECTIONS)}",
                )
            )


def _validate_report(report: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_number("report.min_oos_sharpe", report, issues)
    _optional_number("report.max_oos_drawdown", report, issues, minimum=0, maximum=1)
    _optional_int("report.min_oos_trades", report, issues, minimum=0)
    if "freq" in report:
        _require_timedelta_str("report.freq", report, issues)
    if "year_freq" in report:
        _require_timedelta_str("report.year_freq", report, issues)


def _require_timedelta_str(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    key = path.rsplit(".", 1)[-1]
    if not _require_str(path, mapping, issues):
        return
    value = _parse_timedelta(
        path,
        mapping[key],
        issues,
        message="must be a Timedelta-compatible string",
    )
    if value is None:
        return
    if value <= pd.Timedelta(0):
        issues.append(ConfigValidationIssue(path, "must be positive"))


def _validate_experiment_name(value: str, issues: list[ConfigValidationIssue]) -> None:
    if not EXPERIMENT_NAME_RE.fullmatch(value) or value in {".", ".."}:
        issues.append(
            ConfigValidationIssue(
                "name",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )


def _section(
    raw: dict[str, Any],
    name: str,
    allowed: set[str],
    issues: list[ConfigValidationIssue],
) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(name, "must be a mapping"))
        return {}
    _validate_known_keys(name, value, allowed, issues)
    return value


def _validate_known_keys(
    path: str,
    value: dict[str, Any],
    allowed: set[str],
    issues: list[ConfigValidationIssue],
) -> None:
    for key in sorted(set(value) - allowed):
        child_path = key if path == "$" else f"{path}.{key}"
        issues.append(ConfigValidationIssue(child_path, "unknown field"))


def _validate_passthrough(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_json_like(path, value, issues)
    _validate_no_inline_secrets(path, value, issues)
    _validate_no_denied_passthrough_keys(path, value, issues)


def _validate_no_denied_passthrough_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    _validate_no_denied_keys(
        path,
        value,
        DENIED_PASSTHROUGH_KEYS,
        "is not allowed in passthrough config",
        issues,
    )


def _validate_no_denied_keys(
    path: str,
    value: Any,
    denied_keys: set[str],
    message: str,
    issues: list[ConfigValidationIssue],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in denied_keys:
                issues.append(ConfigValidationIssue(child_path, message))
            _validate_no_denied_keys(child_path, item, denied_keys, message, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_denied_keys(f"{path}[{index}]", item, denied_keys, message, issues)


def _validate_json_like(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if _is_number(value):
        try:
            number = float(value)
        except OverflowError:
            issues.append(ConfigValidationIssue(path, "must be finite"))
            return
        if not math.isfinite(number):
            issues.append(ConfigValidationIssue(path, "must be finite"))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_like(f"{path}[{index}]", item, issues)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                issues.append(
                    ConfigValidationIssue(f"{path}.{key}", "mapping keys must be strings")
                )
                continue
            _validate_json_like(f"{path}.{key}", item, issues)
        return
    issues.append(ConfigValidationIssue(path, "must be JSON-serializable"))


def _require_str(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    allow_none: bool = False,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        issues.append(ConfigValidationIssue(path, "is required"))
        return False
    return _optional_str(path, mapping, issues, allow_none=allow_none)


def _optional_str(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    allow_none: bool = False,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    return _validate_str(path, mapping[key], issues, allow_none=allow_none)


def _validate_str(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    allow_none: bool = False,
) -> bool:
    if value is None and allow_none:
        return True
    if not isinstance(value, str) or not value:
        issues.append(ConfigValidationIssue(path, "must be a non-empty string"))
        return False
    return True


def _optional_str_bool_none(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    if mapping[key] is None or isinstance(mapping[key], str | bool):
        return True
    issues.append(ConfigValidationIssue(path, "must be a string, boolean, or null"))
    return False


def _optional_bool(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    if isinstance(mapping[key], bool):
        return True
    issues.append(ConfigValidationIssue(path, "must be a boolean"))
    return False


def _require_int(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: int | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        issues.append(ConfigValidationIssue(path, "is required"))
        return False
    return _optional_int(path, mapping, issues, positive=positive, minimum=minimum)


def _optional_int(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: int | None = None,
    allow_none: bool = False,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    if mapping[key] is None and allow_none:
        return True
    return _validate_int(path, mapping[key], issues, positive=positive, minimum=minimum)


def _validate_int(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: int | None = None,
) -> bool:
    if not _is_int(value):
        issues.append(ConfigValidationIssue(path, "must be an integer"))
        return False
    if positive and int(value) <= 0:
        issues.append(ConfigValidationIssue(path, "must be positive"))
        return False
    if minimum is not None and int(value) < minimum:
        issues.append(ConfigValidationIssue(path, f"must be at least {minimum}"))
        return False
    return True


def _validate_int_or_int_list(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
) -> bool:
    if isinstance(value, list):
        if not value:
            issues.append(ConfigValidationIssue(path, "must not be empty"))
            return False
        ok = True
        for index, item in enumerate(value):
            ok = _validate_int(f"{path}[{index}]", item, issues, positive=positive) and ok
        return ok
    return _validate_int(path, value, issues, positive=positive)


def _optional_number(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    value = mapping[key]
    if not _is_number(value):
        issues.append(ConfigValidationIssue(path, "must be a number"))
        return False
    try:
        number = float(value)
    except OverflowError:
        issues.append(ConfigValidationIssue(path, "must be finite"))
        return False
    if not math.isfinite(number):
        issues.append(ConfigValidationIssue(path, "must be finite"))
        return False
    if positive and number <= 0:
        issues.append(ConfigValidationIssue(path, "must be positive"))
        return False
    if minimum is not None and number < minimum:
        issues.append(ConfigValidationIssue(path, f"must be at least {minimum}"))
        return False
    if maximum is not None and number > maximum:
        issues.append(ConfigValidationIssue(path, f"must be at most {maximum}"))
        return False
    return True


def _parse_timedelta(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    message: str,
) -> pd.Timedelta | None:
    try:
        return pd.Timedelta(value)
    except (TypeError, ValueError):
        issues.append(ConfigValidationIssue(path, message))
        return None


def _optional_enum(
    path: str,
    mapping: dict[str, Any],
    allowed: set[str],
    issues: list[ConfigValidationIssue],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    value = mapping[key]
    if not isinstance(value, str):
        issues.append(ConfigValidationIssue(path, "must be a string"))
        return False
    if value not in allowed:
        issues.append(ConfigValidationIssue(path, f"must be one of {sorted(allowed)}"))
        return False
    return True


def _require_str_list(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    non_empty: bool = False,
) -> bool:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        issues.append(ConfigValidationIssue(path, "must be a list of non-empty strings"))
        return False
    if non_empty and not value:
        issues.append(ConfigValidationIssue(path, "must not be empty"))
        return False
    return True


def _require_int_list(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
) -> bool:
    if not isinstance(value, list) or not all(_is_int(item) for item in value):
        issues.append(ConfigValidationIssue(path, "must be a list of integers"))
        return False
    if positive and any(int(item) <= 0 for item in value):
        issues.append(ConfigValidationIssue(path, "must contain only positive integers"))
        return False
    return True


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)

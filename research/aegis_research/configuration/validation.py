from __future__ import annotations

import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pandas as pd

from research.aegis_research.component_registry import (
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
    LANE_EXECUTABLE_DENIED_KEYS,
    LANES,
    MISSING_POLICIES,
    MODEL_DENIED_KEYS,
    MODEL_SOURCE_KINDS,
    PORTFOLIO_DIRECTIONS,
    PORTFOLIO_TARGET_SIZE_TYPES,
    RANKING_DIRECTIONS,
    SIGNAL_EXECUTION_TIMINGS,
    SIGNAL_POLICIES,
    SOURCE_KINDS,
    SPLIT_KINDS,
    CandidateGridConfig,
    ConfigValidationIssue,
    DataConfig,
    DataQualityConfig,
    PortfolioConfig,
    ReportConfig,
    RunSplitConfig,
    SignalConfig,
    SplitConfig,
    has_data_array_token_shape,
)
from research.aegis_research.configuration.secrets import _validate_no_inline_secrets
from research.aegis_research.market_data.sources import LOCAL_DATA_SOURCES, remote_data_sources
from research.aegis_research.metrics import FrozenMetricRegistry
from research.aegis_research.model_registry import FrozenModelRegistry
from research.aegis_research.run_splits import validate_run_split_config


def _validate_raw_lane_config(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    model_registry: FrozenModelRegistry | None,
    metric_registry: FrozenMetricRegistry,
    expected_lane: str | None,
) -> None:
    lane = _effective_run_mode(raw, expected_lane)
    _validate_top_level_lane_selection(raw, issues)
    _validate_known_keys("$", raw, _lane_allowed_top_level_keys(lane), issues)
    _require_int("schema_version", raw, issues, positive=True)
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        issues.append(ConfigValidationIssue("schema_version", f"must be {CONFIG_SCHEMA_VERSION}"))
    authored_lane = raw.get("lane")
    if authored_lane is not None:
        if not isinstance(authored_lane, str) or authored_lane not in LANES:
            issues.append(ConfigValidationIssue("lane", f"must be one of {sorted(LANES)}"))
        elif expected_lane is not None and authored_lane != expected_lane:
            issues.append(
                ConfigValidationIssue(
                    "lane",
                    "does not select run mode; use or omit --train instead",
                )
            )
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

    if lane == "run":
        _validate_strategy_run_lane(
            raw,
            issues,
            component_registry=component_registry,
            metric_registry=metric_registry,
        )
    elif lane == "train":
        _validate_train_lane(
            raw,
            issues,
            component_registry=component_registry,
            model_registry=model_registry,
            metric_registry=metric_registry,
        )


def _effective_run_mode(raw: dict[str, Any], expected_lane: str | None) -> str:
    if expected_lane is not None:
        return expected_lane
    authored_lane = raw.get("lane")
    if isinstance(authored_lane, str) and authored_lane in LANES:
        return authored_lane
    if "labeler" in raw and not {"strategy", "ranking"}.intersection(raw):
        return "train"
    if "train" in raw and not {"strategy", "ranking"}.intersection(raw):
        return "train"
    return "run"


def _lane_allowed_top_level_keys(lane: Any) -> set[str]:
    common = {"schema_version", "lane", "name", "data", "portfolio", "report", "output_dir"}
    if lane == "train":
        return common | {"indicators", "labeler", "train"}
    return common | {"candidate_grid", "indicators", "ranking", "split", "strategy"}


def _validate_top_level_lane_selection(
    raw: dict[str, Any], issues: list[ConfigValidationIssue]
) -> None:
    if "strategy" in raw and "labeler" in raw:
        issues.append(
            ConfigValidationIssue(
                "labeler",
                "is mutually exclusive with top-level strategy selection",
            )
        )


def _validate_strategy_run_lane(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> None:
    _validate_training_fields_absent(raw, issues)
    _validate_run_source_ref(
        "strategy",
        raw.get("strategy"),
        "strategies",
        issues,
        component_registry=component_registry,
        allowed_sources={"component", "playbook"},
    )
    _validate_indicator_sources(
        "indicators",
        raw.get("indicators"),
        issues,
        component_registry=component_registry,
        allowed_sources={"component", "playbook"},
    )
    _validate_run_source_combination(raw, issues)
    _validate_ranking("ranking", raw.get("ranking"), issues, lane="run", registry=metric_registry)
    if raw.get("split") is not None:
        split = _section(raw, "split", set(RunSplitConfig.__dataclass_fields__), issues)
        _validate_run_split(split, issues)
    candidate_grid = _section(
        raw,
        "candidate_grid",
        set(CandidateGridConfig.__dataclass_fields__),
        issues,
    )
    _validate_candidate_grid(candidate_grid, issues)


def _validate_run_source_combination(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    strategy = raw.get("strategy")
    if not isinstance(strategy, dict) or strategy.get("source") != "component":
        return
    indicators = raw.get("indicators")
    if not isinstance(indicators, list):
        return
    for index, indicator in enumerate(indicators):
        if isinstance(indicator, dict) and indicator.get("source") == "playbook":
            issues.append(
                ConfigValidationIssue(
                    f"indicators[{index}].source",
                    "playbook indicators cannot enter the component runner; use a playbook "
                    "strategy or promote the indicator candidate to a fixed component",
                )
            )


def _validate_train_lane(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    model_registry: FrozenModelRegistry | None,
    metric_registry: FrozenMetricRegistry,
) -> None:
    if "train" not in raw:
        issues.append(
            ConfigValidationIssue(
                "train",
                "is required for train mode; pass strategy sweeps to aerd run without --train",
            )
        )
        return
    train = _section(
        raw,
        "train",
        {"label", "model", "split", "signals"},
        issues,
    )
    if "label" in train:
        issues.append(
            ConfigValidationIssue(
                "train.label",
                "was removed; move the stable component id to top-level labeler: {id: ...}",
            )
        )
    _validate_labeler_ref(
        "labeler",
        raw.get("labeler"),
        issues,
        component_registry=component_registry,
    )
    _validate_indicator_sources(
        "indicators",
        raw.get("indicators"),
        issues,
        component_registry=component_registry,
        allowed_sources={"component"},
    )
    split = _section(train, "split", set(SplitConfig.__dataclass_fields__), issues)
    signals = _section(train, "signals", set(SignalConfig.__dataclass_fields__), issues)
    _validate_split(split, issues)
    _validate_signals(signals, issues)
    _validate_train_model_ref(
        "train.model", train.get("model"), issues, model_registry=model_registry
    )


def _validate_run_split(split: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_int("split.max_splits", split, issues, positive=True)
    _optional_int("split.max_estimated_output_cells", split, issues, positive=True)
    _optional_int("split.max_public_artifact_bytes", split, issues, positive=True)

    params = split.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue("split.params", "must be a mapping"))
    else:
        _validate_json_like("split.params", params, issues)
        _validate_no_inline_secrets("split.params", params, issues)
        _validate_no_lane_executable_keys("split.params", params, issues)
    validate_run_split_config(split, issues)


def _validate_train_model_ref(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    model_registry: FrozenModelRegistry | None,
) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, {"source", "id", "min_train_samples", "params"}, issues)
    _validate_no_lane_executable_keys(path, value, issues)
    source = value.get("source")
    if not isinstance(source, str) or source not in MODEL_SOURCE_KINDS:
        issues.append(
            ConfigValidationIssue(
                f"{path}.source",
                f"must be one of {sorted(MODEL_SOURCE_KINDS)}",
            )
        )
    model_id = value.get("id")
    if not isinstance(model_id, str) or not model_id:
        issues.append(ConfigValidationIssue(f"{path}.id", "must be a non-empty model id"))
    elif not EXPERIMENT_NAME_RE.fullmatch(model_id):
        issues.append(
            ConfigValidationIssue(
                f"{path}.id",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )
    elif model_registry is not None and model_id not in model_registry:
        issues.append(ConfigValidationIssue(f"{path}.id", "unknown registered model plugin id"))
    _optional_int(f"{path}.min_train_samples", value, issues, positive=True)
    params = value.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue(f"{path}.params", "must be a mapping"))
    else:
        _validate_json_like(f"{path}.params", params, issues)
        _validate_no_inline_secrets(f"{path}.params", params, issues)
        _validate_no_denied_model_keys(f"{path}.params", params, issues)
        _validate_no_lane_executable_keys(f"{path}.params", params, issues)
        if model_registry is not None and isinstance(model_id, str) and model_id in model_registry:
            definition = model_registry.get(model_id)
            if definition.validate_params is not None:
                for param_path, message in definition.validate_params(params).items():
                    child_path = f"{path}.params.{param_path}" if param_path else f"{path}.params"
                    issues.append(ConfigValidationIssue(child_path, message))


def _validate_labeler_ref(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> None:
    if value is None:
        issues.append(ConfigValidationIssue(path, "is required for train mode"))
        return
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, {"id"}, issues)
    _validate_no_lane_executable_keys(path, value, issues)
    labeler_id = value.get("id")
    if not isinstance(labeler_id, str):
        issues.append(ConfigValidationIssue(f"{path}.id", "must be a non-empty stable id"))
        return
    if labeler_id == "":
        issues.append(ConfigValidationIssue(f"{path}.id", "must be a non-empty stable id"))
        return
    if labeler_id == "all":
        issues.append(ConfigValidationIssue(f"{path}.id", "must select one labeler id"))
        return
    if not EXPERIMENT_NAME_RE.fullmatch(labeler_id):
        issues.append(
            ConfigValidationIssue(
                f"{path}.id",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )
        return
    try:
        component_registry.get(ComponentSelection("labels", labeler_id))
    except ComponentRegistryError:
        issues.append(ConfigValidationIssue(f"{path}.id", "unknown label component id"))


def _validate_training_fields_absent(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    for key in ("train", "model", "labels", "label", "labeler", "signals"):
        if key in raw:
            if key == "labeler" and "strategy" in raw:
                continue
            issues.append(
                ConfigValidationIssue(
                    key,
                    "model training fields are not valid at top level; use aerd run --train with a train section",
                )
            )


def _validate_indicator_sources(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    allowed_sources: set[str],
) -> None:
    if isinstance(value, dict) and "specs" in value:
        issues.append(
            ConfigValidationIssue(
                path,
                "must use source refs; legacy indicators.specs is not accepted in lane configs",
            )
        )
        return
    if not isinstance(value, list) or not value:
        issues.append(ConfigValidationIssue(path, "must be a non-empty list"))
        return

    seen: dict[tuple[str, str], str] = {}
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(ConfigValidationIssue(item_path, "must be a mapping"))
            continue
        _validate_known_keys(item_path, item, {"source", "ids"}, issues)
        _validate_no_lane_executable_keys(item_path, item, issues)
        source = item.get("source")
        if not isinstance(source, str) or source not in allowed_sources:
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.source", f"must be one of {sorted(allowed_sources)}"
                )
            )
            continue
        ids = item.get("ids")
        expanded = _validate_indicator_source_ids(
            f"{item_path}.ids",
            ids,
            source,
            issues,
            component_registry=component_registry,
        )
        for indicator_id, id_path in expanded:
            previous = seen.get((source, indicator_id))
            if previous is not None:
                issues.append(
                    ConfigValidationIssue(
                        id_path,
                        f"duplicates expanded {source} indicator id {indicator_id!r} from {previous}",
                    )
                )
                continue
            seen[(source, indicator_id)] = id_path


def _validate_indicator_source_ids(
    path: str,
    value: Any,
    source: str,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> tuple[tuple[str, str], ...]:
    if value == "all":
        ids = component_registry.ids("indicators") if source == "component" else ("all",)
        return tuple((indicator_id, path) for indicator_id in ids)
    if not isinstance(value, list) or not value:
        issues.append(
            ConfigValidationIssue(path, "must be 'all' or a non-empty list of stable ids")
        )
        return ()

    expanded: list[tuple[str, str]] = []
    for index, indicator_id in enumerate(value):
        id_path = f"{path}[{index}]"
        if not isinstance(indicator_id, str) or not indicator_id:
            issues.append(ConfigValidationIssue(id_path, "must be a non-empty stable id"))
            continue
        if indicator_id == "all":
            issues.append(
                ConfigValidationIssue(id_path, "must use ids: all instead of listing 'all'")
            )
            continue
        if not EXPERIMENT_NAME_RE.fullmatch(indicator_id):
            issues.append(
                ConfigValidationIssue(
                    id_path,
                    "must contain only letters, numbers, dots, underscores, and hyphens",
                )
            )
            continue
        if source == "component":
            try:
                component_registry.get(ComponentSelection("indicators", indicator_id))
            except ComponentRegistryError:
                issues.append(ConfigValidationIssue(id_path, "unknown indicator component id"))
                continue
        expanded.append((indicator_id, id_path))
    return tuple(expanded)


def _validate_run_source_ref(
    path: str,
    value: Any,
    family: str,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    allowed_sources: set[str] | None = None,
) -> None:
    _validate_source_ref_value(
        path,
        value,
        family,
        issues,
        component_registry=component_registry,
        allowed_sources=allowed_sources,
        non_string_id_message="must be a non-empty stable id",
        all_id_message="must select one strategy id",
    )


def _validate_source_ref_value(
    path: str,
    value: Any,
    family: str,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    allowed_sources: set[str] | None,
    non_string_id_message: str,
    all_id_message: str,
) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, {"source", "id"}, issues)
    _validate_no_lane_executable_keys(path, value, issues)
    source = value.get("source")
    allowed_source_values = allowed_sources or SOURCE_KINDS
    if not isinstance(source, str) or source not in allowed_source_values:
        issues.append(
            ConfigValidationIssue(
                f"{path}.source", f"must be one of {sorted(allowed_source_values)}"
            )
        )
        return
    component_id = value.get("id")
    if not isinstance(component_id, str):
        issues.append(ConfigValidationIssue(f"{path}.id", non_string_id_message))
        return
    if component_id == "":
        issues.append(ConfigValidationIssue(f"{path}.id", "must be a non-empty stable id"))
        return
    if component_id == "all":
        issues.append(ConfigValidationIssue(f"{path}.id", all_id_message))
        return
    if not EXPERIMENT_NAME_RE.fullmatch(component_id):
        issues.append(
            ConfigValidationIssue(
                f"{path}.id",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )
    if source == "component":
        try:
            component_registry.get(ComponentSelection(family, component_id))
        except ComponentRegistryError:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.id",
                    f"unknown {family[:-1] if family.endswith('s') else family} component id",
                )
            )


def _validate_ranking(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    lane: str,
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
            lane=lane,
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
        lane=lane,
        registry=registry,
    )


def _validate_secondary_metrics(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    primary_metric: str | None,
    lane: str,
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
            lane=lane,
            registry=registry,
            require_primary=False,
        )


def _validate_metric_selection(
    path: str,
    metric_id: str,
    issues: list[ConfigValidationIssue],
    *,
    lane: str,
    registry: FrozenMetricRegistry,
    require_primary: bool,
) -> None:
    if metric_id not in registry:
        issues.append(ConfigValidationIssue(path, f"must be one of {sorted(registry.ids())}"))
        return
    definition = registry.get(metric_id)
    if lane not in definition.supported_lanes:
        issues.append(ConfigValidationIssue(path, f"metric {metric_id!r} is not supported for {lane!r} lane"))
        return
    if require_primary and not definition.primary_eligible:
        issues.append(ConfigValidationIssue(path, f"metric {metric_id!r} is not primary-eligible"))
    if not require_primary and not definition.secondary_eligible:
        issues.append(ConfigValidationIssue(path, f"metric {metric_id!r} is not secondary-eligible"))


def _validate_no_lane_executable_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in LANE_EXECUTABLE_DENIED_KEYS:
                issues.append(
                    ConfigValidationIssue(
                        child_path,
                        "is not allowed in run config; select trusted component or playbook IDs",
                    )
                )
            _validate_no_lane_executable_keys(child_path, item, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_lane_executable_keys(f"{path}[{index}]", item, issues)


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


def _validate_split(split: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    kind = split.get("kind", SplitConfig.kind)
    if not _optional_enum("split.kind", split, SPLIT_KINDS, issues):
        return
    kind = str(kind)
    _validate_purged_kfold_split(split, kind, issues)


def _validate_purged_kfold_split(
    split: dict[str, Any],
    kind: str,
    issues: list[ConfigValidationIssue],
) -> None:
    _optional_int("split.n_folds", split, issues, minimum=2)
    _optional_int("split.n_test_folds", split, issues, positive=True)
    _optional_timedelta("split.purge_td", split, issues, minimum=pd.Timedelta(0))
    _optional_timedelta("split.embargo_td", split, issues, minimum=pd.Timedelta(0))
    _optional_int("split.max_splits", split, issues, positive=True)
    _optional_int("split.max_estimated_output_cells", split, issues, positive=True)
    _optional_int("split.max_public_artifact_bytes", split, issues, positive=True)

    if kind != "purged_kfold":
        return

    n_folds_value = split.get("n_folds", SplitConfig.n_folds)
    n_test_folds_value = split.get("n_test_folds", SplitConfig.n_test_folds)
    max_splits_value = split.get("max_splits", SplitConfig.max_splits)
    if not (_is_int(n_folds_value) and _is_int(n_test_folds_value) and _is_int(max_splits_value)):
        return

    n_folds = int(n_folds_value)
    n_test_folds = int(n_test_folds_value)
    if n_test_folds != 1:
        issues.append(
            ConfigValidationIssue(
                "split.n_test_folds",
                "must be 1 until overlapping CPCV aggregation is supported",
            )
        )
        return
    if n_test_folds >= n_folds:
        issues.append(
            ConfigValidationIssue(
                "split.n_test_folds",
                "must be less than split.n_folds for purged_kfold",
            )
        )
        return
    max_splits = int(max_splits_value)
    split_count = math.comb(n_folds, n_test_folds)
    if split_count > max_splits:
        issues.append(
            ConfigValidationIssue(
                "split.max_splits",
                f"must be at least {split_count} for purged_kfold",
            )
        )


def _validate_signals(signals: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_enum("signals.policy", signals, SIGNAL_POLICIES, issues)
    _optional_enum("signals.execution_timing", signals, SIGNAL_EXECUTION_TIMINGS, issues)
    long_entry_threshold = signals.get("long_entry_threshold", 0.55)
    long_exit_threshold = signals.get("long_exit_threshold", 0.50)
    entry_ok = _optional_number(
        "signals.long_entry_threshold",
        signals,
        issues,
        minimum=0,
        maximum=1,
    )
    exit_ok = _optional_number(
        "signals.long_exit_threshold",
        signals,
        issues,
        minimum=0,
        maximum=1,
    )
    if entry_ok and exit_ok and float(long_exit_threshold) >= float(long_entry_threshold):
        issues.append(
            ConfigValidationIssue(
                "signals.long_exit_threshold",
                "must be less than signals.long_entry_threshold",
            )
        )


def _validate_candidate_grid(
    candidate_grid: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    _optional_int("candidate_grid.max_candidates", candidate_grid, issues, positive=True)
    _optional_int("candidate_grid.max_estimated_cells", candidate_grid, issues, positive=True)
    _optional_int("candidate_grid.batch_size", candidate_grid, issues, positive=True)


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
                    "v1 positive_class_probability signal contract is long-only; use longonly",
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


def _validate_no_denied_model_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    _validate_no_denied_keys(
        path,
        value,
        MODEL_DENIED_KEYS,
        "is not allowed in model config; register trusted plugin code before validation",
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
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
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


def _optional_timedelta(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    minimum: pd.Timedelta | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    value = mapping[key]
    if isinstance(value, bool):
        issues.append(ConfigValidationIssue(path, "must be a timedelta-compatible value"))
        return False
    timedelta = _parse_timedelta(
        path,
        value,
        issues,
        message="must be a timedelta-compatible value",
    )
    if timedelta is None:
        return False
    if minimum is not None and timedelta < minimum:
        issues.append(ConfigValidationIssue(path, f"must be at least {minimum}"))
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

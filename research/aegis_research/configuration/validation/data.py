"""Market-data source, arrays, quality-policy, and path validation.

Validates the ``data`` block: the source must be a supported local or remote provider,
remote sources require symbols/start/end/timeframe, csv requires a relative project-local
path, ``arrays`` must be non-empty VBT feature tokens, and the quality policy must list
known degradations. Owns the filesystem-path safety predicates reused by data loading.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from research.aegis_research.configuration.schema import (
    DATA_ARRAY_SHORTCUTS,
    DATA_QUALITY_DEGRADATIONS,
    MISSING_POLICIES,
    ConfigValidationIssue,
    DataQualityConfig,
    has_data_array_token_shape,
)
from research.aegis_research.configuration.validation.base import (
    _optional_bool,
    _optional_enum,
    _optional_int,
    _optional_str,
    _optional_str_bool_none,
    _require_str_list,
    _validate_known_keys,
    _validate_passthrough,
)
from research.aegis_research.market_data.sources import LOCAL_DATA_SOURCES, remote_data_sources


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

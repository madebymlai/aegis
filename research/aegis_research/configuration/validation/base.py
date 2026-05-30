"""Shared type and structure validators.

Domain-agnostic building blocks used by every domain validator: required/optional
scalar checks, known-key enforcement, JSON-safety, denied-key scans, and the generic
section extractor. No domain imports beyond the schema value types and secrets guard.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import (
    DENIED_PASSTHROUGH_KEYS,
    RUN_EXECUTABLE_DENIED_KEYS,
    ConfigValidationIssue,
)
from research.aegis_research.configuration.secrets import _validate_no_inline_secrets


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


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)

from __future__ import annotations

import os
from typing import Any

from research.aegis_research.configuration.schema import (
    ConfigValidationError,
    ConfigValidationIssue,
)


def _is_env_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"env"}


def resolve_env_refs(value: Any, path: str = "$") -> Any:
    issues: list[ConfigValidationIssue] = []
    resolved = _resolve_env_refs(path, value, issues)
    if issues:
        raise ConfigValidationError(issues)
    return resolved


def _resolve_env_refs(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> Any:
    if _is_env_ref(value):
        env_name = value["env"]
        resolved = os.environ.get(env_name, "")
        if not resolved:
            issues.append(
                ConfigValidationIssue(path, f"environment variable {env_name!r} is not set")
            )
            return None
        return resolved
    if isinstance(value, dict):
        return {
            key: _resolve_env_refs(f"{path}.{key}", item, issues) for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_env_refs(f"{path}[{index}]", item, issues) for index, item in enumerate(value)
        ]
    return value

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

_CANONICAL_JSON_SEPARATORS = (",", ":")

__all__ = ["canonical_json_bytes", "to_builtin"]


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a value to stable UTF-8 JSON bytes."""
    return json.dumps(
        to_builtin(value),
        sort_keys=True,
        separators=_CANONICAL_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")


def to_builtin(value: Any) -> Any:
    """Convert project dataclasses and scalar wrappers into JSON-ready builtins."""
    if _is_resolved_run_config(value):
        return to_builtin(value.config)
    if _is_dataclass_instance(value):
        return {field.name: to_builtin(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "item"):
        return to_builtin(value.item())
    if isinstance(value, Mapping):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_builtin(item) for item in value]
    return value


def _is_resolved_run_config(value: Any) -> bool:
    return value.__class__.__name__ == "ResolvedRunConfig" and hasattr(value, "config")


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)

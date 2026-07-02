from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from nautilus_trader.model.identifiers import InstrumentId

_CANONICAL_JSON_SEPARATORS = (",", ":")
_RESOLVED_RUN_CONFIG_TYPE_NAME = "ResolvedRunConfig"

__all__ = ["canonical_json_bytes", "to_builtin"]


def canonical_json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    """Convert a value to builtins and serialize it to stable UTF-8 JSON bytes."""
    kwargs: dict[str, Any] = {"sort_keys": True, "allow_nan": False}
    if indent is None:
        kwargs["separators"] = _CANONICAL_JSON_SEPARATORS
    else:
        kwargs["indent"] = indent
    return json.dumps(to_builtin(value), **kwargs).encode("utf-8")


def to_builtin(value: Any) -> Any:
    """Recursively convert project dataclasses and scalar wrappers to JSON-ready builtins."""
    if _is_resolved_run_config(value):
        return to_builtin(value.config)
    if isinstance(value, InstrumentId):
        return value.value
    if _is_dataclass_instance(value):
        return {field.name: to_builtin(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "item"):
        return to_builtin(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_builtin(item) for item in value]
    return value


def _is_resolved_run_config(value: Any) -> bool:
    return value.__class__.__name__ == _RESOLVED_RUN_CONFIG_TYPE_NAME and hasattr(value, "config")


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)

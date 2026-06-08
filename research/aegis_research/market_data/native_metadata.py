from __future__ import annotations

from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.canonical_json import to_builtin

_SAFE_NATIVE_METADATA_FIELDS = (
    "last_index",
    "delisted",
    "missing_index",
    "missing_columns",
    "tz_localize",
    "tz_convert",
    "freq",
)


def native_data_metadata(
    native_object: Any,
    *,
    source: str,
    provider_mappings: tuple[tuple[str, set[str]], ...] = (),
) -> dict[str, Any]:
    """Serialize a native data object into a small JSON-safe metadata sidecar.

    Always projects the allowlisted native fields plus ``source``/``class``.
    ``provider_mappings`` adds allowlist projections of provider mappings
    (``fetch_kwargs``/``returned_kwargs``); the remote adapter is the only
    caller that supplies them. The allowlist bounds the projection to a known,
    serializable set — keys outside it are dropped and recorded in ``omitted``.
    """
    omitted: list[dict[str, str]] = []
    metadata: dict[str, Any] = {}
    for name in _SAFE_NATIVE_METADATA_FIELDS:
        if (value := _get_optional_attr(native_object, name)) is not _MISSING:
            _project_field(metadata, omitted, name, value)
    for name, allowed_keys in provider_mappings:
        value = _get_optional_attr(native_object, name)
        if value is _MISSING:
            continue
        projected = _project_provider_mapping(
            value,
            allowed_keys=allowed_keys,
            omitted=omitted,
            path=name,
        )
        if projected:
            metadata[name] = projected
    metadata["source"] = source
    metadata["class"] = f"{type(native_object).__module__}.{type(native_object).__qualname__}"
    return {"metadata": metadata, "omitted": omitted}


def supports_update(native_data: Any) -> bool:
    if getattr(native_data, "feature_oriented", False):
        return _overrides_vectorbt_update_method(native_data, "update_feature")
    if _declares_symbol_orientation(native_data):
        return _overrides_vectorbt_update_method(native_data, "update_symbol")
    return _overrides_vectorbt_update_method(native_data, "update")


def _project_field(
    target: dict[str, Any],
    omitted: list[dict[str, str]],
    name: str,
    value: Any,
) -> None:
    projected = _serializable_value(value, omitted=omitted, path=name)
    if projected is not _OMITTED:
        target[name] = projected


def _project_provider_mapping(
    value: Any,
    *,
    allowed_keys: set[str],
    omitted: list[dict[str, str]],
    path: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        omitted.append({"path": path, "reason": "not a mapping"})
        return {}
    projected: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        child_path = f"{path}.{key_text}"
        if key_text not in allowed_keys:
            omitted.append({"path": child_path, "reason": "field is not allowlisted"})
            continue
        serializable = _serializable_value(item, omitted=omitted, path=child_path)
        if serializable is not _OMITTED:
            projected[key_text] = serializable
    return projected


class _Omitted:
    pass


class _Missing:
    pass


_OMITTED = _Omitted()
_MISSING = _Missing()


def _get_optional_attr(native_object: Any, name: str) -> Any:
    try:
        return getattr(native_object, name)
    except AttributeError:
        return _MISSING


def _serializable_value(value: Any, *, omitted: list[dict[str, str]], path: str) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return to_builtin(value)
    if isinstance(value, pd.Timestamp):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        projected = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            serializable = _serializable_value(item, omitted=omitted, path=child_path)
            if serializable is not _OMITTED:
                projected[key_text] = serializable
        return projected
    if isinstance(value, list | tuple):
        projected = []
        for index, item in enumerate(value):
            serializable = _serializable_value(item, omitted=omitted, path=f"{path}[{index}]")
            if serializable is not _OMITTED:
                projected.append(serializable)
        return projected
    omitted.append({"path": path, "reason": f"unsupported type {type(value).__name__}"})
    return _OMITTED


def _declares_symbol_orientation(native_data: Any) -> bool:
    return _declares_any_attribute(native_data, ("symbol_oriented", "symbols"))


def _declares_any_attribute(native_data: Any, names: tuple[str, ...]) -> bool:
    if any(name in vars(cls) for cls in type(native_data).mro() for name in names):
        return True
    try:
        instance_attributes = vars(native_data)
    except TypeError:
        return False
    return any(name in instance_attributes for name in names)


def _overrides_vectorbt_update_method(native_data: Any, method_name: str) -> bool:
    method = getattr(type(native_data), method_name, None)
    base_method = getattr(vbt.Data, method_name, None)
    return callable(getattr(native_data, method_name, None)) and method is not base_method

from __future__ import annotations

from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import (
    DENIED_PASSTHROUGH_KEYS,
    SECRET_KEY_RE,
    SECRET_VALUE_RE,
)
from research.aegis_research.configuration.secrets import to_builtin
from research.aegis_research.configuration.validation import _is_absolute_or_user_path

_SAFE_NATIVE_METADATA_FIELDS = (
    "last_index",
    "delisted",
    "missing_index",
    "missing_columns",
    "tz_localize",
    "tz_convert",
    "freq",
)


def assert_public_metadata_safe(
    value: Any,
    *,
    known_secrets: tuple[str, ...] = (),
    path: str = "$",
) -> None:
    if isinstance(value, str):
        if _contains_secret_material(value, known_secrets=known_secrets):
            raise ValueError(f"public data metadata contains secret material at {path}")
        if _is_absolute_or_user_path(value):
            raise ValueError(f"public data metadata contains a non-portable path at {path}")
        return
    if value is None or isinstance(value, bool | int | float):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_secret_or_denied_key(key_text):
                raise ValueError(f"public data metadata contains secret-like key at {child_path}")
            assert_public_metadata_safe(item, known_secrets=known_secrets, path=child_path)
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            assert_public_metadata_safe(item, known_secrets=known_secrets, path=f"{path}[{index}]")
        return
    raise ValueError(f"public data metadata contains unsupported value at {path}")


def safe_native_data_metadata(
    native_object: Any,
    *,
    source: str,
    provider_mappings: tuple[tuple[str, set[str]], ...] = (),
) -> dict[str, Any]:
    """Project a native data object into safe, public-shareable provider metadata.

    Always projects the allowlisted safe native fields plus ``source``/``class``.
    ``provider_mappings`` adds allowlist projections of secret-bearing provider
    mappings (``fetch_kwargs``/``returned_kwargs``); the remote adapter is the
    only caller that supplies them, keeping the credential-touching projection
    local to the one source that produces credentials.
    """
    omitted: list[dict[str, str]] = []
    metadata: dict[str, Any] = {}
    for name in _SAFE_NATIVE_METADATA_FIELDS:
        if (value := _get_optional_attr(native_object, name)) is not _MISSING:
            _project_safe_field(metadata, omitted, name, value)
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


def _project_safe_field(
    target: dict[str, Any],
    omitted: list[dict[str, str]],
    name: str,
    value: Any,
) -> None:
    projected = _safe_public_value(value, omitted=omitted, path=name)
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
        if _is_secret_or_denied_key(key_text):
            omitted.append({"path": child_path, "reason": "secret-like or denied key"})
            continue
        if key_text not in allowed_keys:
            omitted.append({"path": child_path, "reason": "field is not allowlisted"})
            continue
        safe_value = _safe_public_value(item, omitted=omitted, path=child_path)
        if safe_value is not _OMITTED:
            projected[key_text] = safe_value
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


def _safe_public_value(value: Any, *, omitted: list[dict[str, str]], path: str) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return to_builtin(value)
    if isinstance(value, pd.Timestamp):
        return str(value)
    if isinstance(value, str):
        if _contains_secret_material(value):
            omitted.append({"path": path, "reason": "secret-like value"})
            return _OMITTED
        if _is_absolute_or_user_path(value):
            omitted.append({"path": path, "reason": "non-portable absolute path"})
            return _OMITTED
        return value
    if isinstance(value, dict):
        projected = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_secret_or_denied_key(key_text):
                omitted.append({"path": child_path, "reason": "secret-like or denied key"})
                continue
            safe_value = _safe_public_value(item, omitted=omitted, path=child_path)
            if safe_value is not _OMITTED:
                projected[key_text] = safe_value
        return projected
    if isinstance(value, list | tuple):
        projected = []
        for index, item in enumerate(value):
            safe_value = _safe_public_value(item, omitted=omitted, path=f"{path}[{index}]")
            if safe_value is not _OMITTED:
                projected.append(safe_value)
        return projected
    omitted.append({"path": path, "reason": f"unsupported type {type(value).__name__}"})
    return _OMITTED


def _contains_secret_material(value: str, *, known_secrets: tuple[str, ...] = ()) -> bool:
    return any(secret and secret in value for secret in known_secrets) or bool(
        SECRET_VALUE_RE.search(value)
    )


def _is_secret_or_denied_key(key: str) -> bool:
    return bool(SECRET_KEY_RE.search(key)) or key.lower() in DENIED_PASSTHROUGH_KEYS


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

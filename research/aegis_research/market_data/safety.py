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
from research.aegis_research.market_data.contracts import (
    SAFE_FETCH_KWARG_KEYS,
    SAFE_RETURNED_KWARG_KEYS,
)


def assert_public_metadata_safe(
    value: Any,
    *,
    known_secrets: tuple[str, ...] = (),
    path: str = "$",
) -> None:
    if isinstance(value, str):
        if any(secret and secret in value for secret in known_secrets) or SECRET_VALUE_RE.search(
            value
        ):
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
            if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_PASSTHROUGH_KEYS:
                raise ValueError(f"public data metadata contains secret-like key at {child_path}")
            assert_public_metadata_safe(item, known_secrets=known_secrets, path=child_path)
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            assert_public_metadata_safe(item, known_secrets=known_secrets, path=f"{path}[{index}]")
        return
    raise ValueError(f"public data metadata contains unsupported value at {path}")


def safe_native_data_metadata(native_object: Any, *, source: str) -> dict[str, Any]:
    omitted: list[dict[str, str]] = []
    metadata: dict[str, Any] = {}
    for name in (
        "last_index",
        "delisted",
        "missing_index",
        "missing_columns",
        "tz_localize",
        "tz_convert",
        "freq",
    ):
        if hasattr(native_object, name):
            _project_safe_field(metadata, omitted, name, getattr(native_object, name))
    for name, allowed_keys in (
        ("fetch_kwargs", SAFE_FETCH_KWARG_KEYS),
        ("returned_kwargs", SAFE_RETURNED_KWARG_KEYS),
    ):
        if hasattr(native_object, name):
            projected = _project_provider_mapping(
                getattr(native_object, name),
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
    if hasattr(native_data, "symbol_oriented") or hasattr(native_data, "symbols"):
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
        if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_PASSTHROUGH_KEYS:
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


_OMITTED = _Omitted()


def _safe_public_value(value: Any, *, omitted: list[dict[str, str]], path: str) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return to_builtin(value)
    if isinstance(value, pd.Timestamp):
        return str(value)
    if isinstance(value, str):
        if SECRET_VALUE_RE.search(value):
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
            if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_PASSTHROUGH_KEYS:
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


def _overrides_vectorbt_update_method(native_data: Any, method_name: str) -> bool:
    method = getattr(type(native_data), method_name, None)
    base_method = getattr(vbt.Data, method_name, None)
    return callable(getattr(native_data, method_name, None)) and method is not base_method

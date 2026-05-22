from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

CANDIDATE_ROW_SCHEMA_VERSION = "candidate_row.v2"
CANDIDATE_IDENTITY_SCHEMA_VERSION = "candidate_identity.v2"
DEFAULT_COORDINATE_LEVELS = frozenset({"split", "set", "symbol"})


def candidate_rows_from_param_index(
    index: pd.Index,
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any] | None = None,
    portfolio_policy: Mapping[str, Any] | None = None,
    store_namespace: Mapping[str, Any] | None = None,
    coordinate_levels: Sequence[str] = tuple(DEFAULT_COORDINATE_LEVELS),
) -> list[dict[str, Any]]:
    level_names, row_values = _index_rows(index)
    coordinate_names = set(coordinate_levels)
    source_identity = _canonical_mapping(source_identity)
    data_identity = _canonical_mapping(data_identity)
    hidden_params = _canonical_mapping(hidden_params or {})
    portfolio_policy = _canonical_mapping(portfolio_policy or {})
    store_namespace = _canonical_mapping(store_namespace or {})
    rows = []
    for row_index, values in enumerate(row_values):
        params: dict[str, Any] = {}
        coordinates: dict[str, Any] = {}
        raw_values: dict[str, Any] = {}
        for name, value in zip(level_names, values, strict=True):
            canonical = canonical_value(value)
            raw_values[name] = canonical
            if name in coordinate_names:
                coordinates[name] = canonical
            else:
                params[name] = canonical
        identity = {
            "schema_version": CANDIDATE_IDENTITY_SCHEMA_VERSION,
            "source_identity": source_identity,
            "data_identity": data_identity,
            "params": params,
            "hidden_params": hidden_params,
            "portfolio_policy": portfolio_policy,
        }
        rows.append(
            {
                "schema_version": CANDIDATE_ROW_SCHEMA_VERSION,
                "row_index": row_index,
                "candidate_key": _candidate_key(identity),
                "store_namespace": store_namespace,
                "params": params,
                "coordinates": coordinates,
                "param_index": {
                    "names": list(level_names),
                    "values": raw_values,
                },
                "identity": identity,
            }
        )
    return rows


def _index_rows(index: pd.Index) -> tuple[tuple[str, ...], Iterable[tuple[Any, ...]]]:
    if isinstance(index, pd.MultiIndex):
        return (
            tuple(_level_name(name, position) for position, name in enumerate(index.names)),
            index,
        )
    return ((_level_name(index.name, 0),), ((value,) for value in index))


def _level_name(name: Any, position: int) -> str:
    if isinstance(name, str) and name:
        return name
    return f"level_{position}"


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): canonical_value(value[key]) for key in sorted(value)}


def canonical_params_key(params: Mapping[str, Any]) -> str:
    canonical = {str(key): canonical_value(params[key]) for key in sorted(params)}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return {
            "kind": "enum",
            "type": f"{type(value).__module__}.{type(value).__qualname__}",
            "name": value.name,
            "value": canonical_value(value.value),
        }
    if value is None:
        return None
    if isinstance(value, np.generic):
        return canonical_value(value.item())
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value):
            return {"kind": "nan"}
        if math.isinf(value):
            return {"kind": "infinity", "sign": 1 if value > 0 else -1}
        return float(value)
    if isinstance(value, pd.Timestamp):
        return {"kind": "timestamp", "value": value.isoformat()}
    if isinstance(value, pd.Timedelta):
        return {"kind": "timedelta", "value": value.isoformat()}
    if isinstance(value, Mapping):
        return _canonical_mapping(value)
    if isinstance(value, tuple | list):
        return [canonical_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return [canonical_value(item) for item in value.tolist()]
    return {
        "kind": "repr",
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "value": repr(value),
    }


def _candidate_key(identity: Mapping[str, Any]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "cand_" + hashlib.sha256(payload.encode()).hexdigest()[:32]

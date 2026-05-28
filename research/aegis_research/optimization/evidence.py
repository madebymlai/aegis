from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)

CANDIDATE_ROW_SCHEMA_VERSION = "candidate_row.v2"
CANDIDATE_IDENTITY_SCHEMA_VERSION = "candidate_identity.v2"
CANDIDATE_EVAL_ROW_SCHEMA_VERSION = "candidate_eval_row.v1"
OPTIMIZATION_RESULT_SCHEMA_VERSION = "optimization_result.v1"
CANDIDATE_ROLES = ("best", "median", "worst")
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
        identity = _candidate_identity(
            params,
            source_identity=source_identity,
            data_identity=data_identity,
            hidden_params=hidden_params,
            portfolio_policy=portfolio_policy,
        )
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


def candidate_rows_from_result(
    result: OptimizationResult,
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any] | None = None,
    portfolio_policy: Mapping[str, Any] | None = None,
    store_namespace: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build one role-tagged candidate row per representative candidate.

    Emits exactly three rows — ``best``, ``median``, ``worst`` — carrying the
    candidate identity (and the ``candidate_key`` derived from it) alongside the
    run-specific ranking attributes ``role``, ``rank``, and ``score`` plus the
    per-split selection/held-out metrics. The same candidate may fill several
    roles (e.g. a single-candidate sweep); rows then share a ``candidate_key``.
    """
    source_identity = _canonical_mapping(source_identity)
    data_identity = _canonical_mapping(data_identity)
    hidden_params = _canonical_mapping(hidden_params or {})
    portfolio_policy = _canonical_mapping(portfolio_policy or {})
    store_namespace = _canonical_mapping(store_namespace or {})
    candidates = (result.best, result.median, result.worst)
    rows = []
    for rank, (role, candidate) in enumerate(zip(CANDIDATE_ROLES, candidates, strict=True), start=1):
        params = _canonical_mapping(candidate.params)
        identity = _candidate_identity(
            params,
            source_identity=source_identity,
            data_identity=data_identity,
            hidden_params=hidden_params,
            portfolio_policy=portfolio_policy,
        )
        rows.append(
            {
                "schema_version": CANDIDATE_EVAL_ROW_SCHEMA_VERSION,
                "role": role,
                "rank": rank,
                "candidate_key": _candidate_key(identity),
                "store_namespace": store_namespace,
                "params": params,
                "score": _optional_float(candidate.score),
                "selection_metrics": _canonical_split_metrics(candidate.selection_metrics),
                "held_out_metrics": _canonical_split_metrics(candidate.held_out_metrics),
                "metrics": _canonical_metric_map(candidate.metrics),
                "identity": identity,
            }
        )
    return rows


def result_evidence(result: OptimizationResult) -> dict[str, Any]:
    """Serialize an OptimizationResult into a JSON-safe three-candidate payload."""
    return {
        "schema_version": OPTIMIZATION_RESULT_SCHEMA_VERSION,
        "best": _candidate_evidence(result.best),
        "median": _candidate_evidence(result.median),
        "worst": _candidate_evidence(result.worst),
    }


def _candidate_evidence(candidate: EvaluatedCandidate) -> dict[str, Any]:
    return {
        "params": _canonical_mapping(candidate.params),
        "score": _optional_float(candidate.score),
        "selection_metrics": _canonical_split_metrics(candidate.selection_metrics),
        "held_out_metrics": _canonical_split_metrics(candidate.held_out_metrics),
        "metrics": _canonical_metric_map(candidate.metrics),
    }


def _candidate_identity(
    params: Mapping[str, Any],
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any],
    portfolio_policy: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_IDENTITY_SCHEMA_VERSION,
        "source_identity": dict(source_identity),
        "data_identity": dict(data_identity),
        "params": dict(params),
        "hidden_params": dict(hidden_params),
        "portfolio_policy": dict(portfolio_policy),
    }


def _canonical_split_metrics(
    metrics: Mapping[Any, Mapping[str, float | None]],
) -> dict[str, dict[str, float | None]]:
    return {
        str(split): {str(metric): _optional_float(value) for metric, value in values.items()}
        for split, values in metrics.items()
    }


def _canonical_metric_map(metrics: Mapping[str, float | None]) -> dict[str, float | None]:
    return {str(metric): _optional_float(value) for metric, value in metrics.items()}


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number


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

"""Canonical published rows and identity for representative Candidates."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.canonical_json import canonical_json_bytes as _canonical_json_bytes
from research.aegis_research.optimization.ranking import OptimizationResult

CANDIDATE_IDENTITY_SCHEMA_VERSION = "candidate_identity.v5"
CANDIDATE_EVAL_ROW_SCHEMA_VERSION = "candidate_eval_row.v3"
CANDIDATE_ROLES = ("best", "median", "worst")
_CANDIDATE_KEY_DIGEST_CHARS = 32


def candidate_rows_from_result(
    result: OptimizationResult,
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    selection_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any] | None = None,
    book_settings: Mapping[str, Any] | None = None,
    store_namespace: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the fixed best/median/worst rows from Observation Block analysis."""
    source_identity = _canonical_mapping(source_identity)
    data_identity = _canonical_mapping(data_identity)
    selection_identity = _canonical_mapping(selection_identity)
    hidden_params = _canonical_mapping(hidden_params or {})
    book_settings = _canonical_mapping(book_settings or {})
    store_namespace = _canonical_mapping(store_namespace or {})
    candidates = (result.best, result.median, result.worst)
    rows = []
    for ordinal, (role, candidate) in enumerate(
        zip(CANDIDATE_ROLES, candidates, strict=True), start=1
    ):
        params = _canonical_mapping(candidate.params)
        identity = _candidate_identity(
            params,
            source_identity=source_identity,
            data_identity=data_identity,
            selection_identity=selection_identity,
            hidden_params=hidden_params,
            book_settings=book_settings,
        )
        rows.append(
            {
                "schema_version": CANDIDATE_EVAL_ROW_SCHEMA_VERSION,
                "role": role,
                "ordinal_rank": ordinal,
                "candidate_key": candidate_key_for_identity(identity),
                "store_namespace": store_namespace,
                "params": params,
                "mean_rank": _optional_float(candidate.score),
                "observation_block_metrics": _canonical_block_metrics(
                    candidate.observation_block_metrics
                ),
                "complete_period_metrics": _canonical_metric_map(candidate.metrics),
                "identity": identity,
            }
        )
    return rows


def _candidate_identity(
    params: Mapping[str, Any],
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    selection_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any],
    book_settings: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_IDENTITY_SCHEMA_VERSION,
        "source_identity": dict(source_identity),
        "data_identity": dict(data_identity),
        "selection_identity": dict(selection_identity),
        "params": dict(params),
        "hidden_params": dict(hidden_params),
        "book_settings": dict(book_settings),
    }


def _canonical_block_metrics(
    metrics: Mapping[Any, Mapping[str, float | None]],
) -> dict[str, dict[str, float | None]]:
    return {
        str(block): {
            str(metric): _optional_float(value) for metric, value in values.items()
        }
        for block, values in metrics.items()
    }


def _canonical_metric_map(metrics: Mapping[str, float | None]) -> dict[str, float | None]:
    return {str(metric): _optional_float(value) for metric, value in metrics.items()}


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): canonical_value(value[key]) for key in sorted(value)}


def canonical_value(value: Any) -> Any:
    """Convert identity inputs to deterministic JSON-safe values."""
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


def candidate_key_for_identity(identity: Mapping[str, Any]) -> str:
    """Return the canonical Candidate key for a complete versioned identity."""
    digest = hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()
    return f"cand_{digest[:_CANDIDATE_KEY_DIGEST_CHARS]}"


__all__ = [
    "CANDIDATE_EVAL_ROW_SCHEMA_VERSION",
    "CANDIDATE_IDENTITY_SCHEMA_VERSION",
    "candidate_key_for_identity",
    "candidate_rows_from_result",
    "canonical_value",
]

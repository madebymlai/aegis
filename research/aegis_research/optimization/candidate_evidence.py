from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.canonical_json import canonical_json_bytes as _canonical_json_bytes
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)

CANDIDATE_ROW_SCHEMA_VERSION = "candidate_row.v2"
CANDIDATE_IDENTITY_SCHEMA_VERSION = "candidate_identity.v3"
CANDIDATE_EVAL_ROW_SCHEMA_VERSION = "candidate_eval_row.v2"
OPTIMIZATION_RESULT_SCHEMA_VERSION = "optimization_result.v3"
CANDIDATE_ROLES = ("best", "median", "worst")
DEFAULT_COORDINATE_LEVELS = frozenset({"split", "set", "symbol"})
_CANDIDATE_KEY_DIGEST_CHARS = 32

# Selection->held-out gap (ranking-metric units) above which the best candidate is
# flagged for selection-set optimism. Calibrated for Sharpe-scale ranking metrics
# (the production default) and mirrors the leak_audit W1 overfit signal.
HELD_OUT_GAP_WARNING_THRESHOLD = 0.5


def candidate_rows_from_param_index(
    index: pd.Index,
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any] | None = None,
    allocation_policy: Mapping[str, Any] | None = None,
    store_namespace: Mapping[str, Any] | None = None,
    coordinate_levels: Sequence[str] = tuple(DEFAULT_COORDINATE_LEVELS),
) -> list[dict[str, Any]]:
    level_names, row_values = _index_rows(index)
    coordinate_names = set(coordinate_levels)
    source_identity = _canonical_mapping(source_identity)
    data_identity = _canonical_mapping(data_identity)
    hidden_params = _canonical_mapping(hidden_params or {})
    allocation_policy = _canonical_mapping(allocation_policy or {})
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
            allocation_policy=allocation_policy,
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
    allocation_policy: Mapping[str, Any] | None = None,
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
    allocation_policy = _canonical_mapping(allocation_policy or {})
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
            allocation_policy=allocation_policy,
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
                "held_out_metrics_mean": _aggregate_split_metrics(candidate.held_out_metrics),
                "identity": identity,
            }
        )
    return rows


def result_evidence(result: OptimizationResult) -> dict[str, Any]:
    """Serialize an OptimizationResult into a JSON-safe three-candidate payload.

    Alongside the three representative candidates, the payload carries the Run's
    exclusion accounting as flat sibling fields: ``total`` is the *exact* number
    of Candidates that entered ranking (never a preflight estimate),
    ``excluded_invalid`` the misconfigured subset, and ``excluded_degenerate``
    the non-representable count, with ``excluded_invalid <= excluded_degenerate
    <= total``.
    """
    return {
        "schema_version": OPTIMIZATION_RESULT_SCHEMA_VERSION,
        "best": _candidate_evidence(result.best),
        "median": _candidate_evidence(result.median),
        "worst": _candidate_evidence(result.worst),
        "total": result.total_candidates,
        "excluded_invalid": result.excluded_invalid,
        "excluded_degenerate": result.excluded_degenerate,
        "non_executable_rows": result.non_executable_rows,
    }


def _candidate_evidence(candidate: EvaluatedCandidate) -> dict[str, Any]:
    return {
        "params": _canonical_mapping(candidate.params),
        "score": _optional_float(candidate.score),
        "selection_metrics": _canonical_split_metrics(candidate.selection_metrics),
        "held_out_metrics": _canonical_split_metrics(candidate.held_out_metrics),
        "metrics": _canonical_metric_map(candidate.metrics),
        "held_out_metrics_mean": _aggregate_split_metrics(candidate.held_out_metrics),
    }


def _aggregate_split_metrics(
    metrics: Mapping[Any, Mapping[str, float | None]],
) -> dict[str, float | None]:
    """Mean of each metric across splits, skipping missing/NaN values.

    The held-out analogue of ``EvaluatedCandidate.metrics`` (the in-sample mean)
    and the aggregation ``leak_audit`` W1 applies to both sets, so the
    selection->held-out gap is computed apples-to-apples. Validated against vbt
    ``sharpe_ratio`` semantics: each split's metric is a self-contained annualized
    scalar (``mean/std * sqrt(ann_factor)``), so a cross-split mean is sound.
    """
    columns: dict[str, list[float]] = {}
    seen: set[str] = set()
    for values in metrics.values():
        for metric, value in values.items():
            key = str(metric)
            seen.add(key)
            number = _optional_float(value)
            if number is not None:
                columns.setdefault(key, []).append(number)
    return {
        metric: (sum(columns[metric]) / len(columns[metric]) if metric in columns else None)
        for metric in sorted(seen)
    }


def candidate_held_out_headline(
    candidate: Mapping[str, Any],
    *,
    metric: str,
) -> dict[str, Any]:
    """Held-out-first view of ``metric`` for a serialized candidate row.

    ``held_out`` is the unbiased out-of-sample aggregate — the number a reader
    should treat as the run's result; ``selection`` is the optimistic in-sample
    aggregate the candidate was *ranked* on; ``gap = selection - held_out``
    quantifies selection-set optimism (mirrors ``leak_audit`` W1). Reads the
    aggregates already serialized on the row (``metrics``, ``held_out_metrics_mean``).
    """
    selection = _optional_float((candidate.get("metrics") or {}).get(metric))
    held_out = _optional_float((candidate.get("held_out_metrics_mean") or {}).get(metric))
    gap = None if selection is None or held_out is None else selection - held_out
    return {
        "metric": metric,
        "held_out": held_out,
        "selection": selection,
        "gap": gap,
    }


def held_out_warning(
    headline: Mapping[str, Any],
    *,
    threshold: float = HELD_OUT_GAP_WARNING_THRESHOLD,
) -> str | None:
    """One-line selection-optimism warning for the best candidate, or ``None``.

    Mirrors ``leak_audit`` W1: warns when the headline held-out ranking metric is
    non-positive (the strategy does not work out-of-sample) or the
    selection->held-out gap is at least ``threshold``.
    """
    metric = headline.get("metric")
    held_out = headline.get("held_out")
    selection = headline.get("selection")
    gap = headline.get("gap")
    if held_out is None:
        return None
    if held_out > 0.0 and not (gap is not None and gap >= threshold):
        return None
    selection_text = "n/a" if selection is None else f"{selection:+.3f}"
    gap_text = "n/a" if gap is None else f"{gap:+.3f}"
    return (
        f"best candidate held-out {metric} {held_out:+.3f} "
        f"(in-sample {selection_text}, gap {gap_text}): selection-set optimism — "
        "treat the in-sample value as a ranking signal, not a result"
    )


def _candidate_identity(
    params: Mapping[str, Any],
    *,
    source_identity: Mapping[str, Any],
    data_identity: Mapping[str, Any],
    hidden_params: Mapping[str, Any],
    allocation_policy: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_IDENTITY_SCHEMA_VERSION,
        "source_identity": dict(source_identity),
        "data_identity": dict(data_identity),
        "params": dict(params),
        "hidden_params": dict(hidden_params),
        "allocation_policy": dict(allocation_policy),
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
    return _canonical_json_bytes(_canonical_mapping(params)).decode()


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
    digest = hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()
    return f"cand_{digest[:_CANDIDATE_KEY_DIGEST_CHARS]}"

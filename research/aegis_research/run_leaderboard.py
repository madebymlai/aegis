from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

RUN_LEADERBOARD_SCHEMA_VERSION = "run_leaderboard.v1"
MAX_LEADERBOARD_ROWS = 10
MAX_FAILURE_SAMPLES = 10


def build_run_leaderboard(
    variant_records: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    direction: str,
    rank_by: str = "primary_metric",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    excluded = 0
    for index, record in enumerate(variant_records):
        variant_id = _variant_id(record, index)
        if "error" in record:
            failures.append(_failure_sample(variant_id, record["error"]))
            continue
        value = _metric_value(record, metric)
        if value is None:
            excluded += 1
            failures.append(_failure_sample(variant_id, f"metric {metric!r} unavailable"))
            continue
        row = _leaderboard_row(record, variant_id, metric, value, direction)
        row["_sort_value"] = _sort_value(row, direction=direction, rank_by=rank_by)
        rows.append(row)

    reverse = rank_by == "baseline_delta" or direction == "desc"
    rows = sorted(rows, key=lambda row: (row["_sort_value"], row["variant_id"]), reverse=reverse)
    rows = [{key: value for key, value in row.items() if key != "_sort_value"} for row in rows]
    attempted = len(variant_records)
    failed = len(failures) - excluded
    succeeded = len(rows)
    return {
        "schema_version": RUN_LEADERBOARD_SCHEMA_VERSION,
        "metric": metric,
        "direction": direction,
        "rank_by": rank_by,
        "rows": rows[:MAX_LEADERBOARD_ROWS],
        "failure_samples": failures[:MAX_FAILURE_SAMPLES],
        "summary": {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "excluded": excluded,
            "success_ratio": succeeded / attempted if attempted else 0.0,
            "partial_leaderboard": bool(failed or excluded),
            "failure_gating_status": "pass" if not failed and not excluded else "partial",
        },
    }


def _leaderboard_row(
    record: Mapping[str, Any],
    variant_id: str,
    metric: str,
    value: float,
    direction: str,
) -> dict[str, Any]:
    row = {
        "variant_id": variant_id,
        "primary_metric": metric,
        "primary_metric_value": value,
        "strategy_source": record.get("strategy_source"),
        "strategy_id": record.get("strategy_id"),
        "indicator_source": record.get("indicator_source"),
        "indicator_id": record.get("indicator_id"),
        "indicators": record.get("indicators", []),
        "params": record.get("params", {}),
        "portfolio": record.get("portfolio", {}),
    }
    baseline_value = _baseline_metric_value(record, metric)
    if baseline_value is not None:
        raw_delta = value - baseline_value
        row |= {
            "baseline_component_indicator_id": record.get("baseline_component_indicator_id"),
            "baseline_metric_value": baseline_value,
            "baseline_delta": raw_delta,
            "direction_adjusted_delta": raw_delta if direction == "desc" else -raw_delta,
        }
    return row


def _metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else record.get(metric)
    return _finite_float(value)


def _baseline_metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("baseline_metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else record.get("baseline_metric_value")
    return _finite_float(value)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _sort_value(row: Mapping[str, Any], *, direction: str, rank_by: str) -> float:
    if rank_by == "baseline_delta" and row.get("direction_adjusted_delta") is not None:
        return float(row["direction_adjusted_delta"])
    if rank_by == "baseline_delta" and direction == "asc":
        return -float(row["primary_metric_value"])
    return float(row["primary_metric_value"])


def _variant_id(record: Mapping[str, Any], index: int) -> str:
    value = record.get("variant_id") or record.get("id")
    if isinstance(value, str) and value:
        return value
    params = record.get("params", {})
    token = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
    return f"variant-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, token)}"


def _failure_sample(variant_id: str, error: Any) -> dict[str, str]:
    if isinstance(error, Mapping):
        code = str(error.get("code", "runtime"))[:80]
        message = str(error.get("message", "failed"))[:300]
    else:
        code = "runtime"
        message = str(error)[:300]
    return {"variant_id": variant_id, "code": code, "message": message}

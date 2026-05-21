from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from research.aegis_research.metrics.custom.baseline_delta import (
    baseline_delta_value,
    baseline_metric_value,
)

RUN_LEADERBOARD_SCHEMA_VERSION = "run_leaderboard.v2"
MAX_LEADERBOARD_ROWS = 10
MAX_FAILURE_SAMPLES = 10
METRIC_SOURCE_CENTRAL_PORTFOLIO = "central_portfolio"


@dataclass(frozen=True)
class _RankedRow:
    sort_value: float
    variant_id: str
    index: int
    row: dict[str, Any]


def build_run_leaderboard(
    candidate_records: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    direction: str,
    secondary_metrics: Sequence[str] = (),
    metric_registry_fingerprint: str | None = None,
) -> dict[str, Any]:
    secondary_metrics = tuple(secondary_metrics)
    ranked_rows: list[_RankedRow] = []
    failures: list[dict[str, str]] = []
    reverse = direction == "desc"
    succeeded = 0
    failed = 0
    excluded = 0
    for index, record in enumerate(candidate_records):
        variant_id = _variant_id(record, index)
        if "error" in record:
            failed += 1
            _append_failure_sample(failures, variant_id, record["error"])
            continue
        _assert_central_metric_source(
            record,
            variant_id,
            metric,
            require_baseline="baseline_delta" in secondary_metrics,
        )
        value = _metric_value(record, metric)
        if value is None:
            excluded += 1
            _append_failure_sample(failures, variant_id, f"metric {metric!r} unavailable")
            continue
        row_metrics = {metric: value}
        missing_metric = _populate_secondary_metrics(
            row_metrics,
            record,
            primary_metric=metric,
            primary_value=value,
            secondary_metrics=secondary_metrics,
        )
        if missing_metric is not None:
            excluded += 1
            _append_failure_sample(failures, variant_id, f"metric {missing_metric!r} unavailable")
            continue
        row = _leaderboard_row(record, variant_id, row_metrics, metric, direction)
        ranked_rows.append(
            _RankedRow(
                sort_value=value,
                variant_id=row["variant_id"],
                index=index,
                row=row,
            )
        )
        ranked_rows.sort(key=lambda item: _ranked_row_key(item, reverse=reverse), reverse=reverse)
        if len(ranked_rows) > MAX_LEADERBOARD_ROWS:
            ranked_rows.pop()
        succeeded += 1

    attempted = len(candidate_records)
    return {
        "schema_version": RUN_LEADERBOARD_SCHEMA_VERSION,
        "primary_metric": metric,
        "direction": direction,
        "secondary_metrics": list(secondary_metrics),
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "rows": [ranked.row for ranked in ranked_rows],
        "failure_samples": failures,
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
    metrics: Mapping[str, float],
    metric: str,
    direction: str,
) -> dict[str, Any]:
    row = {
        "variant_id": variant_id,
        "composed_candidate_id": record.get("composed_candidate_id"),
        "metrics": dict(metrics),
        "strategy_source": record.get("strategy_source"),
        "strategy_id": record.get("strategy_id"),
        "strategy_candidate_id": record.get("strategy_candidate_id"),
        "strategy_candidate_ref": record.get("strategy_candidate_ref"),
        "strategy_params": record.get("strategy_params", record.get("params", {})),
        "indicator_source": record.get("indicator_source"),
        "indicator_id": record.get("indicator_id"),
        "indicators": record.get("indicators", []),
        "indicator_candidates": record.get("indicator_candidates", []),
        "indicator_candidate_refs": record.get("indicator_candidate_refs", []),
        "metric_ref": record.get("metric_ref"),
        "chunk_ref": record.get("chunk_ref"),
        "params": record.get("params", {}),
        "portfolio": record.get("portfolio", {}),
        "metric_source": record.get("metric_source"),
        "source_hash": record.get("source_hash"),
        "component_source_hash": record.get("component_source_hash"),
    }
    baseline_value = baseline_metric_value(record, metric)
    if baseline_value is not None and "baseline_delta" in metrics:
        raw_delta = metrics["baseline_delta"]
        row |= {
            "baseline_component_indicator_id": record.get("baseline_component_indicator_id"),
            "baseline_metric_value": baseline_value,
            "direction_adjusted_delta": raw_delta if direction == "desc" else -raw_delta,
        }
    return row


def _populate_secondary_metrics(
    row_metrics: dict[str, float],
    record: Mapping[str, Any],
    *,
    primary_metric: str,
    primary_value: float,
    secondary_metrics: Sequence[str],
) -> str | None:
    for metric in secondary_metrics:
        if metric == "baseline_delta":
            value = baseline_delta_value(record, primary_metric, primary_value)
        else:
            value = _metric_value(record, metric)
        if value is None:
            return metric
        row_metrics[metric] = value
    return None


def _metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else record.get(metric)
    return _finite_float(value)


def _assert_central_metric_source(
    record: Mapping[str, Any],
    variant_id: str,
    metric: str,
    *,
    require_baseline: bool,
) -> None:
    if record.get("metric_source") != METRIC_SOURCE_CENTRAL_PORTFOLIO:
        raise ValueError(
            f"variant {variant_id!r} metric source must be "
            f"{METRIC_SOURCE_CENTRAL_PORTFOLIO!r}"
        )
    if require_baseline and record.get("baseline_metric_source") != METRIC_SOURCE_CENTRAL_PORTFOLIO:
        raise ValueError(
            f"variant {variant_id!r} baseline metric source must be "
            f"{METRIC_SOURCE_CENTRAL_PORTFOLIO!r}"
        )


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _ranked_row_key(
    item: _RankedRow,
    *,
    reverse: bool,
) -> tuple[float, str, int]:
    return item.sort_value, item.variant_id, -item.index if reverse else item.index


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


def _append_failure_sample(failures: list[dict[str, str]], variant_id: str, error: Any) -> None:
    if len(failures) < MAX_FAILURE_SAMPLES:
        failures.append(_failure_sample(variant_id, error))

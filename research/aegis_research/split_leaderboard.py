from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

MAX_SPLIT_LEADERBOARD_ROWS = 10
SPLIT_LEADERBOARD_SCHEMA_VERSION = "split_run_leaderboard.v1"
METRIC_SOURCE_CENTRAL_PORTFOLIO = "central_portfolio"


def build_split_leaderboard(
    split_metric_records: Sequence[Mapping[str, Any]],
    candidate_records: Mapping[str, Mapping[str, Any]],
    *,
    metric: str,
    direction: str,
    metric_registry_fingerprint: str | None = None,
) -> dict[str, Any]:
    _assert_central_metric_sources(split_metric_records)
    selected_by_split = _selected_candidates_by_split(
        split_metric_records,
        metric=metric,
        direction=direction,
    )
    held_out_by_key = {
        (str(record["split_label"]), str(record["candidate_id"])): record
        for record in split_metric_records
        if record.get("set") == "held_out" and "candidate_id" in record
    }
    aggregate: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    attempted_split_labels = sorted({str(record.get("split_label")) for record in split_metric_records})
    eligible_counts = _eligible_selection_counts(split_metric_records, metric)
    for record in split_metric_records:
        if record.get("set") != "selection" or "candidate_id" not in record:
            continue
        if _metric_value(record, metric) is None:
            _append_failure(
                failures,
                str(record["candidate_id"]),
                f"split {record.get('split_label')} selection metric {metric!r} unavailable",
            )
    for split_label in attempted_split_labels:
        if split_label not in selected_by_split:
            _append_failure(failures, split_label, f"split {split_label} has no selectable candidates")
    for split_label, selection in selected_by_split.items():
        candidate_id = str(selection["candidate_id"])
        held_out = held_out_by_key.get((split_label, candidate_id))
        if held_out is None:
            _append_failure(failures, candidate_id, f"split {split_label} missing held-out metrics")
            continue
        value = _metric_value(held_out, metric)
        if value is None:
            _append_failure(failures, candidate_id, f"split {split_label} metric {metric!r} unavailable")
            continue
        row_count = int(held_out.get("row_count", 0))
        weight = max(row_count, 1)
        item = aggregate.setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "weighted_sum": 0.0,
                "weight": 0,
                "selected_split_count": 0,
                "eligible_split_count": eligible_counts.get(candidate_id, 0),
                "split_refs": [],
                "oos_values": [],
            },
        )
        item["weighted_sum"] += value * weight
        item["weight"] += weight
        item["selected_split_count"] += 1
        item["split_refs"].append(split_label)
        item["oos_values"].append(value)

    rows = []
    for candidate_id, item in aggregate.items():
        value = item["weighted_sum"] / item["weight"]
        base = dict(candidate_records.get(candidate_id, {}))
        rows.append(
            {
                "variant_id": candidate_id,
                "composed_candidate_id": base.get("composed_candidate_id", candidate_id),
                "metrics": {metric: value},
                "metric_source": base.get("metric_source"),
                "strategy_source": base.get("strategy_source"),
                "strategy_id": base.get("strategy_id"),
                "strategy_candidate_id": base.get("strategy_candidate_id"),
                "strategy_candidate_ref": base.get("strategy_candidate_ref"),
                "strategy_params": base.get("strategy_params", base.get("params", {})),
                "indicator_candidates": base.get("indicator_candidates", []),
                "indicator_candidate_refs": base.get("indicator_candidate_refs", []),
                "params": base.get("params", {}),
                "portfolio": base.get("portfolio", {}),
                "selected_split_count": item["selected_split_count"],
                "eligible_split_count": item["eligible_split_count"],
                "split_refs": list(item["split_refs"]),
                "weight_basis": "held_out_row_count",
                "held_out_row_count": item["weight"],
                "oos_metric_values": list(item["oos_values"]),
                "oos_metric_min": min(item["oos_values"]),
                "oos_metric_max": max(item["oos_values"]),
            }
        )

    reverse = direction == "desc"
    rows.sort(key=lambda row: (row["metrics"][metric], row["variant_id"]), reverse=reverse)
    partial = bool(failures)
    return {
        "schema_version": SPLIT_LEADERBOARD_SCHEMA_VERSION,
        "primary_metric": metric,
        "direction": direction,
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "weight_basis": "held_out_row_count",
        "rows": rows[:MAX_SPLIT_LEADERBOARD_ROWS],
        "failure_samples": failures[:10],
        "summary": {
            "attempted_splits": len(attempted_split_labels),
            "selected_splits": sum(item["selected_split_count"] for item in aggregate.values()),
            "candidate_count": len(candidate_records),
            "partial_leaderboard": partial,
            "failure_gating_status": "partial" if partial else "pass",
        },
    }


def _selected_candidates_by_split(
    records: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    direction: str,
) -> dict[str, Mapping[str, Any]]:
    reverse = direction == "desc"
    selected: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if record.get("set") != "selection" or "candidate_id" not in record:
            continue
        value = _metric_value(record, metric)
        if value is None:
            continue
        split_label = str(record["split_label"])
        current = selected.get(split_label)
        if current is None:
            selected[split_label] = record
            continue
        current_value = _metric_value(current, metric)
        if current_value is None:
            selected[split_label] = record
            continue
        key = (value, str(record["candidate_id"]))
        current_key = (current_value, str(current["candidate_id"]))
        if (key > current_key) if reverse else (key < current_key):
            selected[split_label] = record
    return selected


def _metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else None
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _eligible_selection_counts(
    records: Sequence[Mapping[str, Any]],
    metric: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.get("set") != "selection" or "candidate_id" not in record:
            continue
        if _metric_value(record, metric) is None:
            continue
        candidate_id = str(record["candidate_id"])
        counts[candidate_id] = counts.get(candidate_id, 0) + 1
    return counts


def _assert_central_metric_sources(records: Sequence[Mapping[str, Any]]) -> None:
    for record in records:
        if "candidate_id" not in record:
            continue
        if record.get("metric_source") != METRIC_SOURCE_CENTRAL_PORTFOLIO:
            raise ValueError(
                f"rolling split metric for candidate {record['candidate_id']!r} must use "
                f"{METRIC_SOURCE_CENTRAL_PORTFOLIO!r}"
            )


def _append_failure(failures: list[dict[str, str]], candidate_id: str, message: str) -> None:
    if len(failures) < 10:
        failures.append({"variant_id": candidate_id, "code": "rolling_metric", "message": message})

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from research.aegis_research.metrics.contracts import (
    LANE_RUN,
    SOURCE_TYPE_ADAPTER,
    MetricDefinition,
)


def baseline_delta_definition() -> MetricDefinition:
    return MetricDefinition(
        id="baseline_delta",
        title="Baseline Delta",
        source_type=SOURCE_TYPE_ADAPTER,
        unit="metric_delta",
        value_semantics="candidate_primary_minus_baseline_primary",
        supported_lanes=(LANE_RUN,),
        primary_eligible=False,
        secondary_eligible=True,
        direction_hint=None,
        required_inputs=("selected_primary_metric", "candidate_metric", "baseline_metric"),
        provider="aegis",
        target="run_leaderboard",
        source_method="contextual_secondary",
    )


def baseline_delta_value(
    record: Mapping[str, Any],
    primary_metric: str,
    primary_value: float,
) -> float | None:
    baseline_value = baseline_metric_value(record, primary_metric)
    if baseline_value is None:
        return None
    return primary_value - baseline_value


def baseline_metric_value(record: Mapping[str, Any], primary_metric: str) -> float | None:
    metrics = record.get("baseline_metrics", {})
    value = (
        metrics.get(primary_metric)
        if isinstance(metrics, Mapping)
        else record.get("baseline_metric_value")
    )
    return _finite_float(value)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None

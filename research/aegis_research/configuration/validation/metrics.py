"""Ranking and Metric-selection validation.

Validates the ``ranking`` block: the selection Metric must exist in the frozen Metric
registry, ``min_weight`` is a 0..1 blend, and ``min_trades`` is a non-negative floor.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.base import _validate_known_keys
from research.aegis_research.metrics import FrozenMetricRegistry


def _validate_ranking(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    registry: FrozenMetricRegistry,
) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(
        path,
        value,
        {"metric", "min_weight", "min_trades"},
        issues,
    )
    metric = value.get("metric")
    if not isinstance(metric, str) or not metric:
        issues.append(ConfigValidationIssue(f"{path}.metric", "must be a non-empty string"))
    else:
        _validate_metric_selection(
            f"{path}.metric",
            metric,
            issues,
            registry=registry,
        )
    if "min_weight" in value:
        min_weight = value["min_weight"]
        if (
            isinstance(min_weight, bool)
            or not isinstance(min_weight, (int, float))
            or not 0.0 <= float(min_weight) <= 1.0
        ):
            issues.append(
                ConfigValidationIssue(f"{path}.min_weight", "must be a number between 0.0 and 1.0")
            )
    if "min_trades" in value:
        min_trades = value["min_trades"]
        if isinstance(min_trades, bool) or not isinstance(min_trades, int) or min_trades < 0:
            issues.append(
                ConfigValidationIssue(f"{path}.min_trades", "must be a non-negative integer")
            )


def _validate_metric_selection(
    path: str,
    metric_id: str,
    issues: list[ConfigValidationIssue],
    *,
    registry: FrozenMetricRegistry,
) -> None:
    if metric_id not in registry:
        issues.append(ConfigValidationIssue(path, f"must be one of {sorted(registry.ids())}"))

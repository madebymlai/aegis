from __future__ import annotations

from research.aegis_research.metrics.custom.baseline_delta import baseline_delta_definition
from research.aegis_research.metrics.registry import MetricRegistry


def register_custom_metrics(registry: MetricRegistry) -> None:
    registry.register(baseline_delta_definition())


__all__ = [
    "baseline_delta_definition",
    "register_custom_metrics",
]

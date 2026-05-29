from __future__ import annotations

from research.aegis_research.metrics.registry import MetricRegistry


def register_custom_metrics(registry: MetricRegistry) -> None:
    """Registration hook for adapter/custom metrics; none are defined yet."""


__all__ = [
    "register_custom_metrics",
]

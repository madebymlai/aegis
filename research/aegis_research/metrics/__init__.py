from __future__ import annotations

from research.aegis_research.metrics.contracts import (
    DIRECTION_ASC,
    DIRECTION_DESC,
    LANE_RUN,
    LANE_TRAIN,
    SOURCE_TYPE_ADAPTER,
    SOURCE_TYPE_CUSTOM,
    SOURCE_TYPE_VBT_STATS,
    MetricDefinition,
    MetricRegistryError,
)
from research.aegis_research.metrics.registry import (
    FrozenMetricRegistry,
    MetricRegistry,
    empty_metric_registry,
    freeze_metric_registry,
)


def make_default_metric_registry() -> FrozenMetricRegistry:
    from research.aegis_research.metrics.custom import register_custom_metrics
    from research.aegis_research.metrics.stats import register_vbt_stats_metrics

    registry = MetricRegistry()
    register_vbt_stats_metrics(registry)
    register_custom_metrics(registry)
    return registry.freeze()

__all__ = [
    "DIRECTION_ASC",
    "DIRECTION_DESC",
    "FrozenMetricRegistry",
    "LANE_RUN",
    "LANE_TRAIN",
    "MetricDefinition",
    "MetricRegistry",
    "MetricRegistryError",
    "SOURCE_TYPE_ADAPTER",
    "SOURCE_TYPE_CUSTOM",
    "SOURCE_TYPE_VBT_STATS",
    "empty_metric_registry",
    "freeze_metric_registry",
    "make_default_metric_registry",
]

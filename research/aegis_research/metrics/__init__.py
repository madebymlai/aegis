from __future__ import annotations

from research.aegis_research.metrics.contracts import (
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


def make_metric_registry_for(metric_ids: tuple[str, ...]) -> FrozenMetricRegistry:
    """Default registry plus only the optional custom metrics actually requested.

    Custom metrics are opt-in per run: a registry (and its fingerprint, which
    flows into Evidence) carries a custom metric only when a requested metric
    id names one. Unknown ids are not an error here — config validation
    cross-checks the requested metric against the built registry and fails
    closed there.
    """
    from research.aegis_research.metrics.custom import (
        optional_custom_metrics,
        register_custom_metrics,
    )
    from research.aegis_research.metrics.stats import register_vbt_stats_metrics

    optional = optional_custom_metrics()
    requested = tuple(
        optional[metric_id] for metric_id in metric_ids if metric_id in optional
    )
    registry = MetricRegistry()
    register_vbt_stats_metrics(registry)
    register_custom_metrics(registry, metrics=requested)
    return registry.freeze()

__all__ = [
    "SOURCE_TYPE_CUSTOM",
    "SOURCE_TYPE_VBT_STATS",
    "FrozenMetricRegistry",
    "MetricDefinition",
    "MetricRegistry",
    "MetricRegistryError",
    "empty_metric_registry",
    "freeze_metric_registry",
    "make_default_metric_registry",
]

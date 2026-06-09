"""Custom metric registration hook.

Callers register custom metrics (MetricDefinition + ExtractorSpec pairs)
through ``register_custom_metrics``.  Both the definition and the extractor
are fed into the shared registry-driven extraction loop — no further wiring
is required.
"""

from __future__ import annotations

from collections.abc import Sequence

from research.aegis_research.metrics.contracts import MetricDefinition
from research.aegis_research.metrics.extractors import ExtractorSpec, register_custom_extractors
from research.aegis_research.metrics.registry import MetricRegistry


def register_custom_metrics(
    registry: MetricRegistry,
    *,
    metrics: Sequence[tuple[MetricDefinition, ExtractorSpec]] | None = None,
) -> None:
    """Registration hook for custom metrics.

    Each entry is a ``(MetricDefinition, ExtractorSpec)`` pair.  Both are
    registered so the metric is computed by the same registry-driven
    extraction loop as the built-in metrics, with no extra wiring.

    Args:
        registry: The mutable MetricRegistry to register definitions into.
        metrics: Optional sequence of (definition, extractor) pairs.
    """
    if metrics is None:
        return

    extractors_map: dict[str, ExtractorSpec] = {}
    for definition, spec in metrics:
        registry.register(definition)
        extractors_map[definition.id] = spec

    if extractors_map:
        register_custom_extractors(extractors_map)


__all__ = [
    "register_custom_metrics",
]

"""Custom metric registration hook.

Callers register custom metrics as ``(MetricDefinition, ExtractorSpec)`` pairs
through ``register_custom_metrics``. Each pair becomes one registry record —
the same record shape the built-in metrics use — so a custom metric is computed
by the shared registry-driven extraction loop with no further wiring, and its
extractor lives and dies with the registry it was registered into (no global
state).
"""

from __future__ import annotations

from collections.abc import Sequence

from research.aegis_research.metrics.contracts import ExtractorSpec, MetricDefinition
from research.aegis_research.metrics.registry import MetricRegistry


def register_custom_metrics(
    registry: MetricRegistry,
    *,
    metrics: Sequence[tuple[MetricDefinition, ExtractorSpec]] | None = None,
) -> None:
    """Registration hook for custom metrics.

    Each entry is a ``(MetricDefinition, ExtractorSpec)`` pair registered as one
    record, so the metric is computed by the same registry-driven extraction loop
    as the built-in metrics.

    Args:
        registry: The mutable MetricRegistry to register the records into.
        metrics: Optional sequence of (definition, extractor) pairs.
    """
    if metrics is None:
        return
    for definition, spec in metrics:
        registry.register(definition, spec)


__all__ = [
    "register_custom_metrics",
]

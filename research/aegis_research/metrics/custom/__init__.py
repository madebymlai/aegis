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


def optional_custom_metrics() -> dict[str, tuple[MetricDefinition, ExtractorSpec]]:
    """Available opt-in custom metrics, keyed by each definition's own id.

    One flat tuple of records is the only thing a new custom metric module has
    to join; the id keys are derived from the definitions, never written twice.
    Nothing here registers itself: a custom metric enters a registry only when
    a caller (``make_metric_registry_for``) passes its record through
    ``register_custom_metrics`` because a run requested it.
    """
    from research.aegis_research.metrics.custom.ulcer import (
        ULCER_PERFORMANCE_INDEX_DEFINITION,
        ULCER_PERFORMANCE_INDEX_EXTRACTOR,
    )

    available: tuple[tuple[MetricDefinition, ExtractorSpec], ...] = (
        (ULCER_PERFORMANCE_INDEX_DEFINITION, ULCER_PERFORMANCE_INDEX_EXTRACTOR),
    )
    return {definition.id: (definition, spec) for definition, spec in available}


__all__ = [
    "optional_custom_metrics",
    "register_custom_metrics",
]

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from research.aegis_research.metrics.contracts import (
    METRIC_DIRECTIONS,
    METRIC_SOURCE_TYPES,
    MetricDefinition,
    MetricRegistryError,
)


@dataclass(frozen=True)
class FrozenMetricRegistry:
    definitions: Mapping[str, MetricDefinition]
    fingerprint: str

    def get(self, metric_id: str) -> MetricDefinition:
        try:
            return self.definitions[metric_id]
        except KeyError as error:
            raise MetricRegistryError(f"unknown metric id: {metric_id}") from error

    def ids(self) -> tuple[str, ...]:
        return tuple(self.definitions)

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "metrics": {
                metric_id: definition.public_snapshot()
                for metric_id, definition in self.definitions.items()
            },
        }

    def selected_snapshot(self, metric_ids: tuple[str, ...]) -> dict[str, Any]:
        return {
            metric_id: self.get(metric_id).public_snapshot() for metric_id in metric_ids
        }

    def __contains__(self, metric_id: str) -> bool:
        return metric_id in self.definitions


class MetricRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}

    def register(self, definition: MetricDefinition) -> None:
        _validate_definition(definition)
        if definition.id in self._definitions:
            raise MetricRegistryError(f"duplicate metric id: {definition.id}")
        self._definitions[definition.id] = definition

    def freeze(self) -> FrozenMetricRegistry:
        definitions = dict(sorted(self._definitions.items()))
        return FrozenMetricRegistry(
            definitions=MappingProxyType(definitions),
            fingerprint=_registry_fingerprint(definitions),
        )


def empty_metric_registry() -> MetricRegistry:
    return MetricRegistry()


def freeze_metric_registry(
    registry: MetricRegistry | FrozenMetricRegistry | None,
) -> FrozenMetricRegistry | None:
    if registry is None:
        return None
    if isinstance(registry, FrozenMetricRegistry):
        return registry
    return registry.freeze()


def _validate_definition(definition: MetricDefinition) -> None:
    if not definition.id:
        raise MetricRegistryError("metric id must be non-empty")
    if definition.id.strip() != definition.id:
        raise MetricRegistryError(f"metric id must not contain surrounding whitespace: {definition.id!r}")
    if not definition.title:
        raise MetricRegistryError(f"metric {definition.id} title must be non-empty")
    if definition.source_type not in METRIC_SOURCE_TYPES:
        raise MetricRegistryError(f"metric {definition.id} source type is unsupported")
    if not definition.unit:
        raise MetricRegistryError(f"metric {definition.id} unit must be non-empty")
    if not definition.value_semantics:
        raise MetricRegistryError(f"metric {definition.id} value semantics must be non-empty")
    if definition.direction_hint is not None and definition.direction_hint not in METRIC_DIRECTIONS:
        raise MetricRegistryError(f"metric {definition.id} direction hint is unsupported")
    if not definition.primary_eligible and not definition.secondary_eligible:
        raise MetricRegistryError(
            f"metric {definition.id} must be primary or secondary eligible"
        )


def _registry_fingerprint(definitions: Mapping[str, MetricDefinition]) -> str:
    payload = {
        metric_id: definition.fingerprint_payload()
        for metric_id, definition in sorted(definitions.items())
    }
    data = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.metrics.contracts import (
    METRIC_SOURCE_TYPES,
    ExtractorSpec,
    MetricDefinition,
    MetricRegistryError,
)


@dataclass(frozen=True)
class FrozenMetricRegistry:
    definitions: Mapping[str, MetricDefinition]
    fingerprint: str
    extractors: Mapping[str, ExtractorSpec]

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
                metric_id: {
                    **definition.public_snapshot(),
                    "extractor_contract_version": self.extractors[metric_id].contract_version,
                }
                for metric_id, definition in self.definitions.items()
            },
        }

    def __contains__(self, metric_id: str) -> bool:
        return metric_id in self.definitions


@dataclass(frozen=True, init=False)
class ResolvedMetrics:
    registry: FrozenMetricRegistry
    ranking: MetricDefinition

    def __init__(self) -> None:
        raise TypeError("ResolvedMetrics must be constructed with ResolvedMetrics.resolve")

    @classmethod
    def resolve(
        cls, registry: FrozenMetricRegistry, ranking_id: str
    ) -> ResolvedMetrics:
        resolved = object.__new__(cls)
        object.__setattr__(resolved, "registry", registry)
        object.__setattr__(resolved, "ranking", registry.get(ranking_id))
        return resolved


class MetricRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}
        self._extractors: dict[str, ExtractorSpec] = {}

    def register(self, definition: MetricDefinition, extractor: ExtractorSpec) -> None:
        """Register a Metric as one record: its definition and its extractor.

        ``extractor`` is required, so a definition can never enter the registry
        without a way to compute it (catalog-only drift is a missing argument at
        the call) and an extractor can never exist without a definition (it has
        no other registration path). Registration order is preserved for
        extraction; ``freeze`` sorts independently for the fingerprint.
        """
        _validate_definition(definition)
        if definition.id in self._definitions:
            raise MetricRegistryError(f"duplicate metric id: {definition.id}")
        self._definitions[definition.id] = definition
        self._extractors[definition.id] = extractor

    def freeze(self) -> FrozenMetricRegistry:
        definitions = dict(sorted(self._definitions.items()))
        return FrozenMetricRegistry(
            definitions=MappingProxyType(definitions),
            fingerprint=_registry_fingerprint(definitions, self._extractors),
            extractors=MappingProxyType(dict(self._extractors)),
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
        raise MetricRegistryError(
            f"metric id must not contain surrounding whitespace: {definition.id!r}"
        )
    if not definition.title:
        raise MetricRegistryError(f"metric {definition.id} title must be non-empty")
    if definition.source_type not in METRIC_SOURCE_TYPES:
        raise MetricRegistryError(f"metric {definition.id} source type is unsupported")
    if not definition.unit:
        raise MetricRegistryError(f"metric {definition.id} unit must be non-empty")
    if not definition.value_semantics:
        raise MetricRegistryError(f"metric {definition.id} value semantics must be non-empty")
    if definition.direction not in ("maximize", "minimize"):
        raise MetricRegistryError(f"metric {definition.id} direction is unsupported")
    if definition.missing_value_policy != "worst":
        raise MetricRegistryError(f"metric {definition.id} missing-value policy is unsupported")
    if definition.boundary_semantics not in (
        "native_continuous",
        "inherited_path",
        "block_local",
    ):
        raise MetricRegistryError(f"metric {definition.id} boundary semantics are unsupported")


def _registry_fingerprint(
    definitions: Mapping[str, MetricDefinition],
    extractors: Mapping[str, ExtractorSpec],
) -> str:
    payload = {
        metric_id: {
            "definition": definition.fingerprint_payload(),
            "extractor_contract_version": extractors[metric_id].contract_version,
        }
        for metric_id, definition in sorted(definitions.items())
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

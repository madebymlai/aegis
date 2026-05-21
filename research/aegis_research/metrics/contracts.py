from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SOURCE_TYPE_VBT_STATS = "vbt_stats"
SOURCE_TYPE_CUSTOM = "custom"
SOURCE_TYPE_ADAPTER = "adapter"
METRIC_SOURCE_TYPES = (SOURCE_TYPE_VBT_STATS, SOURCE_TYPE_CUSTOM, SOURCE_TYPE_ADAPTER)

DIRECTION_ASC = "asc"
DIRECTION_DESC = "desc"
METRIC_DIRECTIONS = (DIRECTION_ASC, DIRECTION_DESC)


class MetricRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    title: str
    source_type: str
    unit: str
    value_semantics: str
    primary_eligible: bool
    secondary_eligible: bool
    direction_hint: str | None = None
    required_inputs: Sequence[str] = ()
    provider: str = "aegis"
    target: str | None = None
    vbt_metric: str | None = None
    source_method: str | None = None
    required_report_output: bool = False
    required_gate_input: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_inputs", tuple(self.required_inputs))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source_type": self.source_type,
            "unit": self.unit,
            "value_semantics": self.value_semantics,
            "primary_eligible": self.primary_eligible,
            "secondary_eligible": self.secondary_eligible,
            "direction_hint": self.direction_hint,
            "required_inputs": list(self.required_inputs),
            "provider": self.provider,
            "target": self.target,
            "vbt_metric": self.vbt_metric,
            "source_method": self.source_method,
            "required_report_output": self.required_report_output,
            "required_gate_input": self.required_gate_input,
            "metadata": dict(self.metadata),
        }

    def fingerprint_payload(self) -> dict[str, Any]:
        return self.public_snapshot()

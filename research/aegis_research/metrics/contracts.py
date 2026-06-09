from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

SOURCE_TYPE_VBT_STATS = "vbt_stats"
SOURCE_TYPE_CUSTOM = "custom"
METRIC_SOURCE_TYPES = (SOURCE_TYPE_VBT_STATS, SOURCE_TYPE_CUSTOM)


class MetricRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractorSpec:
    """Declarative spec for a single Metric's vectorised batch read.

    ``read`` makes exactly one VBT accessor call over the whole grouped batch
    and returns a per-group value (a Series, or a scalar for a one-group batch);
    ``scale``/``abs_`` are transform flags the extraction loop applies — they are
    deliberately NOT baked into the read. An ``ExtractorSpec`` is the value half
    of a Metric's registry record (``MetricDefinition`` is the identity half);
    it carries a callable and so is never part of the fingerprint payload.
    """

    read: Callable[..., Any]
    scale: Literal["percent", "identity"] = "identity"
    abs_: bool = False


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    title: str
    source_type: str
    unit: str
    value_semantics: str
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

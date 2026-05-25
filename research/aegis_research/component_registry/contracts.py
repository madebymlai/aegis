from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ComponentFamily = Literal["indicators", "strategies"]
COMPONENT_FAMILIES: tuple[ComponentFamily, ...] = ("indicators", "strategies")


class ComponentRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentSelection:
    family: ComponentFamily
    id: str


@dataclass(frozen=True)
class ComponentSourceIdentity:
    repo_relative_path: str
    source_hash: str

    def public(self) -> dict[str, str]:
        return {
            "repo_relative_path": self.repo_relative_path,
            "source_hash": self.source_hash,
        }


@dataclass(frozen=True)
class ComponentManifest:
    family: ComponentFamily
    id: str
    version: str
    payload: Mapping[str, Any]

    def fingerprint_payload(self) -> Mapping[str, Any]:
        return self.payload


@dataclass(frozen=True)
class IndicatorManifest(ComponentManifest):
    input_names: tuple[str, ...]
    param_names: tuple[str, ...]
    output_names: tuple[str, ...]
    defaults: Mapping[str, Any]
    param_space_callable: str | None = None
    bar_aligned: bool = True


@dataclass(frozen=True)
class StrategyManifest(ComponentManifest):
    """Strategy component manifest.

    `output_name` is the declared allocation-native channel emitted by the
    component. It must be one of the four registered shapes — `active`,
    `scores`, `ranks`, or `target_weights` — consumed by the portfolio policy
    layer (see `STRATEGY_ALLOCATION_OUTPUTS`). Legacy `entries`/`exits`
    signal pairs are rejected.
    """

    input_names: tuple[str, ...]
    param_names: tuple[str, ...]
    output_name: str
    consumes_outputs: tuple[str, ...]
    defaults: Mapping[str, Any]
    param_space_callable: str | None = None
    owns_portfolio: bool = False


@dataclass(frozen=True)
class ComponentDefinition:
    manifest: IndicatorManifest | StrategyManifest
    callable_name: str
    file_path: Path
    identity: ComponentSourceIdentity

    @property
    def family(self) -> ComponentFamily:
        return self.manifest.family

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def input_names(self) -> tuple[str, ...]:
        return self.manifest.input_names

    def load_callable(self) -> Any:
        from research.aegis_research.component_registry.registry import load_component_callable

        return load_component_callable(self)

    def load_attribute(self, attribute_name: str) -> Any:
        from research.aegis_research.component_registry.registry import load_component_attribute

        return load_component_attribute(self, attribute_name)

    def load_attributes(self, attribute_names: Sequence[str]) -> dict[str, Any]:
        from research.aegis_research.component_registry.registry import load_component_attributes

        return load_component_attributes(self, tuple(attribute_names))

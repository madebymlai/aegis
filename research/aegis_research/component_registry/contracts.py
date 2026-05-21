from __future__ import annotations

from collections.abc import Mapping
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
    bar_aligned: bool = True


@dataclass(frozen=True)
class StrategyManifest(ComponentManifest):
    input_names: tuple[str, ...]
    signal_outputs: tuple[str, ...]
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

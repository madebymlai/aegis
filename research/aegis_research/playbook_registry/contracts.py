from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

PlaybookFamily = Literal["indicators", "strategies"]
PLAYBOOK_FAMILIES: tuple[PlaybookFamily, ...] = ("indicators", "strategies")
PLAYBOOK_STAGES = frozenset(PLAYBOOK_FAMILIES)


class PlaybookRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class PlaybookSelection:
    family: PlaybookFamily
    id: str


@dataclass(frozen=True)
class PlaybookSourceIdentity:
    repo_relative_path: str
    source_hash: str

    def public(self) -> dict[str, str]:
        return {
            "repo_relative_path": self.repo_relative_path,
            "source_hash": self.source_hash,
        }


@dataclass(frozen=True)
class PlaybookManifest:
    family: PlaybookFamily
    id: str
    version: str
    stages: tuple[str, ...]
    accepted_inputs: tuple[str, ...]
    result_schema: str
    payload: Mapping[str, Any]
    indicator_family: str | None = None
    baseline_component_indicator_id: str | None = None

    def fingerprint_payload(self) -> Mapping[str, Any]:
        return self.payload


@dataclass(frozen=True)
class PlaybookDefinition:
    manifest: PlaybookManifest
    file_path: Path
    identity: PlaybookSourceIdentity
    callable_name: str

    @property
    def family(self) -> PlaybookFamily:
        return self.manifest.family

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def input_names(self) -> tuple[str, ...]:
        return self.manifest.accepted_inputs

    def load_callable(self) -> Any:
        from research.aegis_research.playbook_registry.registry import load_playbook_callable

        return load_playbook_callable(self)


NotebookPlaybookManifest = PlaybookManifest
NotebookPlaybookDefinition = PlaybookDefinition

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from enum import Enum
from typing import Any

from research.aegis_research.canonical_json import to_builtin

OPTIMIZATION_ROUTE_SCHEMA_VERSION = "optimization_route.v1"
_FAILURE_MESSAGE_LIMIT = 1000

__all__ = [
    "EvidenceFailureStage",
    "EvidenceSection",
    "RunEvidence",
]


class EvidenceSection(str, Enum):
    PREFLIGHT = "preflight"
    EXECUTION = "execution"
    CANDIDATES = "candidates"
    LOCKS = "locks"


class EvidenceFailureStage(str, Enum):
    SETUP = "setup"
    PREFLIGHT = "preflight"
    EXECUTION = "execution"
    PUBLISHING = "publishing"
    COMPLETION = "completion"


class RunEvidence:
    """Typed writer for the run manifest evidence payload.

    The ledger writes directly into the manifest's live ``evidence`` mapping so
    recorder persists always serialize the same canonical store. ``snapshot`` is
    a read-only convenience for callers that need a detached builtin view.
    """

    def __init__(
        self,
        manifest_evidence: MutableMapping[str, Any],
        *,
        component_registry_fingerprint: str,
        data_arrays: Mapping[str, Any],
        optimization: Mapping[str, Any],
        persist: Callable[[], None],
    ) -> None:
        self._manifest_evidence = manifest_evidence
        self._persist = persist
        optimization_payload = _optimization_payload(optimization)
        self._manifest_evidence.clear()
        self._manifest_evidence.update(
            {
                "component_registry_fingerprint": component_registry_fingerprint,
                "data_arrays": to_builtin(data_arrays),
                "optimization": optimization_payload,
            }
        )
        self._optimization = optimization_payload

    def record(self, section: EvidenceSection, payload: Any) -> None:
        if not isinstance(section, EvidenceSection):
            raise TypeError("section must be an EvidenceSection")
        builtin_payload = to_builtin(payload)
        self._optimization[section.value] = builtin_payload
        if section is EvidenceSection.CANDIDATES:
            self._optimization["candidate_count"] = _candidate_count(builtin_payload)

    def fail(self, stage: EvidenceFailureStage, err: BaseException) -> None:
        if not isinstance(stage, EvidenceFailureStage):
            raise TypeError("stage must be an EvidenceFailureStage")
        self._optimization[f"{stage.value}_failure"] = {
            "error_type": type(err).__name__,
            "message": str(err)[:_FAILURE_MESSAGE_LIMIT],
        }
        self._persist()

    def snapshot(self) -> dict[str, Any]:
        return to_builtin(self._manifest_evidence)


def _optimization_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    optimization = to_builtin(payload)
    if not isinstance(optimization, dict):
        raise TypeError("optimization evidence must be a mapping")
    schema_version = optimization.get("schema_version")
    if schema_version not in {None, OPTIMIZATION_ROUTE_SCHEMA_VERSION}:
        raise ValueError("unsupported optimization evidence schema_version")
    optimization["schema_version"] = OPTIMIZATION_ROUTE_SCHEMA_VERSION
    return optimization


def _candidate_count(payload: Any) -> int:
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
        raise TypeError("candidates evidence must be a sequence of mappings")
    candidate_keys: set[str] = set()
    for row in payload:
        if not isinstance(row, Mapping):
            raise TypeError("candidate evidence rows must be mappings")
        candidate_key = row.get("candidate_key")
        if not isinstance(candidate_key, str) or not candidate_key:
            raise ValueError("candidate evidence rows require a non-empty candidate_key")
        candidate_keys.add(candidate_key)
    return len(candidate_keys)

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from research.aegis_research.run.identity import RunId

REPRESENTATIVE_ROLES = ("best", "median", "worst")


@dataclass(frozen=True)
class CandidateSet:
    """The complete representative Candidate batch committed for one Run."""

    run_id: RunId
    candidates: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        run_id: RunId,
        candidates: Sequence[Mapping[str, Any]],
        provenance: Mapping[str, Any],
    ) -> CandidateSet:
        copied_candidates = tuple(MappingProxyType(dict(candidate)) for candidate in candidates)
        copied_provenance = MappingProxyType(dict(provenance))
        return cls(
            run_id=run_id,
            candidates=copied_candidates,
            provenance=copied_provenance,
        )


__all__ = ["REPRESENTATIVE_ROLES", "CandidateSet"]

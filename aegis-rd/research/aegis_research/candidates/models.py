from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from research.aegis_research.run.identity import RunId


class InvalidCandidateSetError(ValueError):
    """A Candidate Set is incomplete or internally inconsistent."""


class RepresentativeRole(StrEnum):
    BEST = "best"
    MEDIAN = "median"
    WORST = "worst"


REPRESENTATIVE_ROLES = tuple(RepresentativeRole)
REPRESENTATIVE_ROLE_VALUES = tuple(role.value for role in REPRESENTATIVE_ROLES)

_CANDIDATE_FIELDS = (
    "schema_version",
    "role",
    "ordinal_rank",
    "candidate_key",
    "store_namespace",
    "params",
    "mean_rank",
    "observation_block_metrics",
    "complete_period_metrics",
    "identity",
)


@dataclass(frozen=True)
class Candidate(Mapping[str, Any]):
    """One immutable representative Candidate prepared for durable commit."""

    schema_version: str
    role: RepresentativeRole
    ordinal_rank: int
    candidate_key: str
    store_namespace: Mapping[str, Any]
    params: Mapping[str, Any]
    mean_rank: float | None
    observation_block_metrics: Mapping[str, Any]
    complete_period_metrics: Mapping[str, Any]
    identity: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.role, RepresentativeRole):
            raise InvalidCandidateSetError("Candidate role must be a RepresentativeRole")
        if isinstance(self.ordinal_rank, bool) or not isinstance(self.ordinal_rank, int):
            raise InvalidCandidateSetError("Candidate ordinal_rank must be an integer")
        if self.mean_rank is not None and (
            isinstance(self.mean_rank, bool) or not isinstance(self.mean_rank, int | float)
        ):
            raise InvalidCandidateSetError("Candidate mean_rank must be numeric or null")
        for field_name in ("schema_version", "candidate_key"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise InvalidCandidateSetError(f"Candidate {field_name} must be non-empty text")
        for field_name in (
            "store_namespace",
            "params",
            "observation_block_metrics",
            "complete_period_metrics",
            "identity",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_mapping({field_name: getattr(self, field_name)}, field_name),
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Candidate:
        missing = set(_CANDIDATE_FIELDS) - set(value)
        extra = set(value) - set(_CANDIDATE_FIELDS)
        if missing or extra:
            raise InvalidCandidateSetError(
                f"Candidate fields differ from the contract; missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )
        try:
            role = RepresentativeRole(value["role"])
        except (TypeError, ValueError) as error:
            raise InvalidCandidateSetError(
                "Candidate Set requires unique best, median, and worst roles"
            ) from error
        return cls(
            schema_version=value["schema_version"],
            role=role,
            ordinal_rank=value["ordinal_rank"],
            candidate_key=value["candidate_key"],
            store_namespace=value["store_namespace"],
            params=value["params"],
            mean_rank=value["mean_rank"],
            observation_block_metrics=value["observation_block_metrics"],
            complete_period_metrics=value["complete_period_metrics"],
            identity=value["identity"],
        )

    def __getitem__(self, key: str) -> Any:
        if key not in _CANDIDATE_FIELDS:
            raise KeyError(key)
        value = getattr(self, key)
        return value.value if isinstance(value, RepresentativeRole) else value

    def __iter__(self) -> Iterator[str]:
        return iter(_CANDIDATE_FIELDS)

    def __len__(self) -> int:
        return len(_CANDIDATE_FIELDS)


@dataclass(frozen=True)
class CandidateSet:
    """The complete representative Candidate batch committed for one Run."""

    run_id: RunId
    candidates: tuple[Candidate, ...]
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not all(isinstance(candidate, Candidate) for candidate in self.candidates):
            raise InvalidCandidateSetError("Candidate Set requires typed Candidates")
        object.__setattr__(
            self,
            "provenance",
            _required_mapping({"provenance": self.provenance}, "provenance"),
        )
        self._validate()

    @classmethod
    def create(
        cls,
        *,
        run_id: RunId,
        candidates: Sequence[Mapping[str, Any]],
        provenance: Mapping[str, Any],
    ) -> CandidateSet:
        typed_candidates = tuple(Candidate.from_mapping(candidate) for candidate in candidates)
        return cls(
            run_id=run_id,
            candidates=typed_candidates,
            provenance=provenance,
        )

    def _validate(self) -> None:
        if self.provenance.get("run_id") != str(self.run_id):
            raise InvalidCandidateSetError(
                "Candidate Set provenance run_id does not match its Run ID"
            )
        if not self.candidates:
            raise InvalidCandidateSetError(
                "completed optimization run has no candidate rows to persist"
            )
        if len(self.candidates) != len(REPRESENTATIVE_ROLES):
            raise InvalidCandidateSetError(
                "Candidate Set requires exactly three representative roles"
            )
        roles = tuple(candidate.role for candidate in self.candidates)
        if set(roles) != set(REPRESENTATIVE_ROLES) or len(set(roles)) != len(roles):
            raise InvalidCandidateSetError(
                "Candidate Set requires unique best, median, and worst roles"
            )
        expected_ordinals = dict(zip(REPRESENTATIVE_ROLES, (1, 2, 3), strict=True))
        ordinals = {candidate.role: candidate.ordinal_rank for candidate in self.candidates}
        if ordinals != expected_ordinals:
            raise InvalidCandidateSetError("Candidate Set representative ordinals are inconsistent")


def _required_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value[key]
    if not isinstance(item, Mapping):
        raise InvalidCandidateSetError(f"Candidate {key} must be a mapping")
    return MappingProxyType({str(name): _freeze(nested) for name, nested in item.items()})


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


__all__ = [
    "REPRESENTATIVE_ROLES",
    "REPRESENTATIVE_ROLE_VALUES",
    "Candidate",
    "CandidateSet",
    "InvalidCandidateSetError",
    "RepresentativeRole",
]

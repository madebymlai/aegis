from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)


class PromotionResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentPromotionRef:
    component_family: str
    component_id: str
    component_slot: str
    lock_id: str | None = None
    candidate_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ResolvedPromotion:
    reference_kind: str
    component_family: str
    component_id: str
    component_slot: str
    candidate_key: str
    run_id: str
    params: dict[str, Any]
    provenance: dict[str, Any]


def resolve_component_promotion(
    ref: ComponentPromotionRef,
    *,
    store: CandidateStore,
) -> ResolvedPromotion:
    _validate_reference(ref)
    if ref.lock_id is not None:
        return _resolve_lock(ref, store=store)
    return _resolve_candidate(ref, store=store)


def _validate_reference(ref: ComponentPromotionRef) -> None:
    if bool(ref.lock_id) == bool(ref.candidate_id):
        raise PromotionResolutionError("exactly one of lock_id or candidate_id is required")


def _resolve_lock(ref: ComponentPromotionRef, *, store: CandidateStore) -> ResolvedPromotion:
    assert ref.lock_id is not None
    try:
        row = store.promotion_by_token(ref.lock_id)
    except CandidateStoreError as error:
        raise PromotionResolutionError(str(error)) from error
    _assert_component_match(ref, row)
    return ResolvedPromotion(
        reference_kind="lock_id",
        component_family=ref.component_family,
        component_id=ref.component_id,
        component_slot=ref.component_slot,
        candidate_key=row["candidate_key"],
        run_id=row["run_id"],
        params=dict(row["params"]),
        provenance=dict(row["provenance"]),
    )


def _resolve_candidate(ref: ComponentPromotionRef, *, store: CandidateStore) -> ResolvedPromotion:
    assert ref.candidate_id is not None
    try:
        row = store.candidate_by_key(ref.candidate_id, run_id=ref.run_id)
    except CandidateStoreError as error:
        raise PromotionResolutionError(str(error)) from error
    provenance = dict(row["provenance"])
    provenance.setdefault("component_family", ref.component_family)
    provenance.setdefault("component_id", ref.component_id)
    provenance.setdefault("component_slot", ref.component_slot)
    return ResolvedPromotion(
        reference_kind="candidate_id",
        component_family=ref.component_family,
        component_id=ref.component_id,
        component_slot=ref.component_slot,
        candidate_key=row["candidate_key"],
        run_id=row["run_id"],
        params=dict(row["params"]),
        provenance=provenance,
    )


def _assert_component_match(ref: ComponentPromotionRef, row: dict[str, Any]) -> None:
    mismatches = [
        name
        for name in ("component_family", "component_id", "component_slot")
        if row[name] != getattr(ref, name)
    ]
    if mismatches:
        fields = ", ".join(mismatches)
        raise PromotionResolutionError(
            f"promotion token {row['token']!r} does not belong to requested component ({fields})"
        )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.aegis_research.component_registry import ComponentFamily
from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.component_source import (
    ComponentSourceError,
    component_param_slices,
    component_params_from_slices,
)


class LockResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentLockRef:
    component_family: ComponentFamily
    component_id: str
    component_slot: str
    lock_id: str | None = None
    candidate_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ResolvedLock:
    reference_kind: str
    component_family: ComponentFamily
    component_id: str
    component_slot: str
    candidate_key: str
    run_id: str
    params: dict[str, Any]
    provenance: dict[str, Any]


def resolve_component_lock(
    ref: ComponentLockRef,
    *,
    store: CandidateStore,
) -> ResolvedLock:
    _validate_reference(ref)
    if ref.lock_id is not None:
        return _resolve_lock(ref, store=store)
    return _resolve_candidate(ref, store=store)


def _validate_reference(ref: ComponentLockRef) -> None:
    if bool(ref.lock_id) == bool(ref.candidate_id):
        raise LockResolutionError("exactly one of lock_id or candidate_id is required")


def _resolve_lock(ref: ComponentLockRef, *, store: CandidateStore) -> ResolvedLock:
    assert ref.lock_id is not None
    try:
        row = store.lock_by_token(ref.lock_id)
    except CandidateStoreError as error:
        raise LockResolutionError(str(error)) from error
    _assert_component_match(ref, row)
    return ResolvedLock(
        reference_kind="lock_id",
        component_family=ref.component_family,
        component_id=ref.component_id,
        component_slot=ref.component_slot,
        candidate_key=row["candidate_key"],
        run_id=row["run_id"],
        params=dict(row["params"]),
        provenance=dict(row["provenance"]),
    )


def _resolve_candidate(ref: ComponentLockRef, *, store: CandidateStore) -> ResolvedLock:
    assert ref.candidate_id is not None
    try:
        row = store.candidate_by_key(ref.candidate_id, run_id=ref.run_id)
    except CandidateStoreError as error:
        raise LockResolutionError(str(error)) from error
    provenance = dict(row["provenance"])
    provenance.setdefault("component_family", ref.component_family)
    provenance.setdefault("component_id", ref.component_id)
    provenance.setdefault("component_slot", ref.component_slot)
    params = _component_params_from_candidate(
        ref,
        candidate_params=row["params"],
        provenance=provenance,
    )
    return ResolvedLock(
        reference_kind="candidate_id",
        component_family=ref.component_family,
        component_id=ref.component_id,
        component_slot=ref.component_slot,
        candidate_key=row["candidate_key"],
        run_id=row["run_id"],
        params=params,
        provenance=provenance,
    )


def _assert_component_match(ref: ComponentLockRef, row: dict[str, Any]) -> None:
    mismatches = [
        name
        for name in ("component_family", "component_id", "component_slot")
        if row[name] != getattr(ref, name)
    ]
    if mismatches:
        fields = ", ".join(mismatches)
        raise LockResolutionError(
            f"lock token {row['token']!r} does not belong to requested component ({fields})"
        )


def _component_params_from_candidate(
    ref: ComponentLockRef,
    *,
    candidate_params: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    runtime = _candidate_component_runtime(ref, provenance)
    try:
        slices = component_param_slices(candidate_params)
        return component_params_from_slices(
            component_family=ref.component_family,
            component_id=ref.component_id,
            component_slot=ref.component_slot,
            component_slices=slices,
            runtime=runtime,
            candidate_key=str(ref.candidate_id),
        )
    except ComponentSourceError as error:
        raise LockResolutionError(str(error)) from error


def _candidate_component_runtime(
    ref: ComponentLockRef,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    source = provenance.get("source")
    if not isinstance(source, dict):
        raise LockResolutionError(
            f"candidate key {ref.candidate_id!r} has no component source provenance"
        )
    runtimes = [source.get("strategy"), *source.get("indicators", [])]
    for runtime in runtimes:
        if not isinstance(runtime, dict):
            continue
        if (
            runtime.get("family") == ref.component_family
            and runtime.get("id") == ref.component_id
            and runtime.get("slot") == ref.component_slot
        ):
            return runtime
    raise LockResolutionError(
        f"candidate key {ref.candidate_id!r} does not include component "
        f"{ref.component_family}/{ref.component_id} slot {ref.component_slot!r}"
    )

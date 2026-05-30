from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes as _canonical_json_bytes
from research.aegis_research.component_registry import (
    COMPONENT_FAMILIES,
    ComponentFamily,
)
from research.aegis_research.config import to_builtin
from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.canonical import mint_canonical_token
from research.aegis_research.optimization.component_source import (
    ComponentSourceError,
    component_param_slices,
    component_params_from_slices,
    component_ref_key,
)
from research.aegis_research.optimization.source import OptimizationSourceError

COMPONENT_LOCK_SCHEMA_VERSION = "component_lock.v1"
COMPONENT_LOCK_PROVENANCE_SCHEMA_VERSION = "component_lock_provenance.v1"


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


def resolve_component_locks(
    config: Any,
    *,
    candidate_store_path: str | Path,
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]]]:
    refs = list(_component_lock_refs(config))
    if not refs:
        return {}, []
    resolved_params: dict[tuple[str, str, str], dict[str, Any]] = {}
    resolved_records: list[dict[str, Any]] = []
    with CandidateStore(candidate_store_path) as candidate_store:
        for key, ref in refs:
            resolved = resolve_component_lock(ref, store=candidate_store)
            if key in resolved_params:
                raise OptimizationSourceError(f"duplicate lock resolution for component {key}")
            resolved_params[key] = dict(resolved.params)
            resolved_records.append(_resolved_lock_record(resolved))
    return resolved_params, resolved_records


def build_component_lock_records(
    *,
    run_id: str,
    best_candidate: Mapping[str, Any] | None,
    optimization_source: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not best_candidate:
        return []
    candidate_key = str(best_candidate["candidate_key"])
    candidate_params = dict(best_candidate.get("params", {}))
    component_slices = component_param_slices(candidate_params)
    records: list[dict[str, Any]] = []
    for runtime in _lock_runtime_records(optimization_source):
        component_family = _component_family(runtime["family"])
        component_id = str(runtime["id"])
        component_slot = str(runtime["slot"])
        try:
            params = component_params_from_slices(
                component_family=component_family,
                component_id=component_id,
                component_slot=component_slot,
                component_slices=component_slices,
                runtime=runtime,
                candidate_key=candidate_key,
            )
        except ComponentSourceError as error:
            raise OptimizationSourceError(str(error)) from error
        token = _build_component_lock_token(
            run_id=run_id,
            rank=1,
            component_family=component_family,
            component_id=component_id,
            component_slot=component_slot,
            candidate_key=candidate_key,
        )
        provenance = {
            "schema_version": COMPONENT_LOCK_PROVENANCE_SCHEMA_VERSION,
            "run_id": run_id,
            "rank": 1,
            "candidate_key": candidate_key,
            "component_family": component_family,
            "component_id": component_id,
            "component_slot": component_slot,
            "source": optimization_source,
            "candidate": dict(best_candidate),
        }
        records.append(
            {
                "schema_version": COMPONENT_LOCK_SCHEMA_VERSION,
                "token": token,
                "reference_kind": "lock_id",
                "run_id": run_id,
                "rank": 1,
                "component_family": component_family,
                "component_id": component_id,
                "component_slot": component_slot,
                "candidate_key": candidate_key,
                "params": to_builtin(params),
                "provenance": to_builtin(provenance),
            }
        )
    return records


# -- internal helpers -------------------------------------------------------


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
    runtimes = [source.get("strategy"), *source.get("indicators", ())]
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


def _component_lock_refs(
    config: Any,
) -> Iterator[tuple[tuple[str, str, str], ComponentLockRef]]:
    if config.strategy.lock_id is not None or config.strategy.candidate_id is not None:
        key = component_ref_key("strategies", config.strategy.id, "strategy")
        yield (
            key,
            ComponentLockRef(
                component_family="strategies",
                component_id=config.strategy.id,
                component_slot="strategy",
                lock_id=config.strategy.lock_id,
                candidate_id=config.strategy.candidate_id,
                run_id=config.strategy.run_id,
            ),
        )
    for ref in config.indicators:
        if ref.lock_id is None and ref.candidate_id is None:
            continue
        key = component_ref_key("indicators", ref.id, ref.id)
        yield (
            key,
            ComponentLockRef(
                component_family="indicators",
                component_id=ref.id,
                component_slot=ref.id,
                lock_id=ref.lock_id,
                candidate_id=ref.candidate_id,
                run_id=ref.run_id,
            ),
        )


def _resolved_lock_record(resolved: ResolvedLock) -> dict[str, Any]:
    return {
        "schema_version": "resolved_component_lock.v1",
        "reference_kind": resolved.reference_kind,
        "component_family": resolved.component_family,
        "component_id": resolved.component_id,
        "component_slot": resolved.component_slot,
        "candidate_key": resolved.candidate_key,
        "run_id": resolved.run_id,
        "params": to_builtin(resolved.params),
        "provenance": to_builtin(resolved.provenance),
    }


def _lock_runtime_records(optimization_source: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = [optimization_source.get("strategy"), *optimization_source.get("indicators", ())]
    return [dict(r) for r in candidates if isinstance(r, Mapping)]


def _component_family(value: Any) -> ComponentFamily:
    if value not in COMPONENT_FAMILIES:
        raise OptimizationSourceError(f"unknown component family in optimization source: {value!r}")
    return value


def component_lock_token_bytes(
    *,
    run_id: str,
    rank: int,
    component_family: str,
    component_id: str,
    component_slot: str,
    candidate_key: str,
) -> bytes:
    """Canonical JSON bytes used as stable hash material for component locks."""
    identity = _component_lock_identity(
        run_id=run_id,
        rank=rank,
        component_family=component_family,
        component_id=component_id,
        component_slot=component_slot,
        candidate_key=candidate_key,
    )
    return _canonical_json_bytes(identity)


def _build_component_lock_token(
    *,
    run_id: str,
    rank: int,
    component_family: str,
    component_id: str,
    component_slot: str,
    candidate_key: str,
) -> str:
    identity = _component_lock_identity(
        run_id=run_id,
        rank=rank,
        component_family=component_family,
        component_id=component_id,
        component_slot=component_slot,
        candidate_key=candidate_key,
    )
    return mint_canonical_token("lock", identity)


def _component_lock_identity(
    *,
    run_id: str,
    rank: int,
    component_family: str,
    component_id: str,
    component_slot: str,
    candidate_key: str,
) -> dict[str, Any]:
    return {
        "schema_version": COMPONENT_LOCK_SCHEMA_VERSION,
        "run_id": run_id,
        "rank": rank,
        "component_family": component_family,
        "component_id": component_id,
        "component_slot": component_slot,
        "candidate_key": candidate_key,
    }

"""Top-level Lock run-resolution: reproduce one prior Candidate across every Component.

A ``Lock`` is the transparent ``(run_id, candidate_id)`` pair — exactly the ``candidates``
primary key ``(run_id, candidate_key)``. This deep module is the single seam between a
``Lock`` and the per-Component params a locked Run feeds to the optimization source: it
loads the Candidate by its primary key and fans the Candidate's parameters across every
Component the Candidate was produced from, using the existing component-param slicing.

It is independent of the legacy per-Component lock machinery (``lock_resolution``), which
this slice leaves untouched and coexisting.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from research.aegis_research.component_registry import (
    COMPONENT_FAMILIES,
    ComponentFamily,
)
from research.aegis_research.configuration.schema import Lock
from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.component_source import (
    ComponentSourceError,
    component_param_slices,
    component_params_from_slices,
)

LOCK_RUN_PROVENANCE_SCHEMA_VERSION = "lock_run_provenance.v1"

# (component_family, component_id, component_slot) -> param-name -> value
ResolvedComponentParams = dict[tuple[ComponentFamily, str, str], dict[str, Any]]


class LockRunResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedLockRun:
    """Every Component's params, drawn from the one Candidate a Lock reproduces."""

    run_id: str
    candidate_key: str
    component_params: ResolvedComponentParams
    provenance: dict[str, Any]


def resolve_lock_run(lock: Lock, *, store: CandidateStore) -> ResolvedLockRun:
    """Resolve a ``Lock`` to the per-Component params of the Candidate it reproduces."""
    try:
        row = store.candidate_by_key(lock.candidate_id, run_id=lock.run_id)
    except CandidateStoreError as error:
        raise LockRunResolutionError(
            f"unknown candidate for lock run_id={lock.run_id!r} "
            f"candidate_id={lock.candidate_id!r}: {error}"
        ) from error

    runtimes = _candidate_component_runtimes(lock, row["provenance"])
    candidate_slices = component_param_slices(row["params"])
    component_params: ResolvedComponentParams = {}
    for runtime in runtimes:
        family = _component_family(runtime["family"])
        component_id = str(runtime["id"])
        component_slot = str(runtime["slot"])
        try:
            params = component_params_from_slices(
                component_family=family,
                component_id=component_id,
                component_slot=component_slot,
                component_slices=candidate_slices,
                runtime=runtime,
                candidate_key=row["candidate_key"],
            )
        except ComponentSourceError as error:
            raise LockRunResolutionError(str(error)) from error
        component_params[(family, component_id, component_slot)] = params

    _assert_every_slice_resolved(lock, candidate_slices, component_params)

    return ResolvedLockRun(
        run_id=row["run_id"],
        candidate_key=row["candidate_key"],
        component_params=component_params,
        provenance={
            "schema_version": LOCK_RUN_PROVENANCE_SCHEMA_VERSION,
            "run_id": row["run_id"],
            "candidate_id": row["candidate_key"],
            "candidate": dict(row["provenance"]),
        },
    )


def _assert_every_slice_resolved(
    lock: Lock,
    candidate_slices: Mapping[tuple[str, str, str], Mapping[str, Any]],
    component_params: ResolvedComponentParams,
) -> None:
    orphaned = sorted(set(candidate_slices) - set(component_params))
    if orphaned:
        family, component_id, component_slot = orphaned[0]
        raise LockRunResolutionError(
            f"candidate {lock.candidate_id!r} does not include component "
            f"{family}/{component_id} slot {component_slot!r} in its source provenance, "
            f"but its params reference it"
        )


def _candidate_component_runtimes(
    lock: Lock,
    provenance: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source = provenance.get("source")
    if not isinstance(source, Mapping):
        raise LockRunResolutionError(
            f"candidate {lock.candidate_id!r} has no component source provenance"
        )
    runtimes = [source.get("strategy"), *source.get("indicators", ())]
    resolved = [dict(runtime) for runtime in runtimes if isinstance(runtime, Mapping)]
    if not resolved:
        raise LockRunResolutionError(
            f"candidate {lock.candidate_id!r} does not include component runtimes"
        )
    return resolved


def _component_family(value: Any) -> ComponentFamily:
    if value not in COMPONENT_FAMILIES:
        raise LockRunResolutionError(f"unknown component family in candidate provenance: {value!r}")
    return value

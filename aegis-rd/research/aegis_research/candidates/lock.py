"""Top-level Lock run-resolution: reproduce one prior Candidate across every Component.

A ``Lock`` is the transparent ``(run_id, candidate_id)`` pair — exactly the ``candidates``
primary key ``(run_id, candidate_key)``. This deep module is the single seam between a
``Lock`` and the per-Component params a locked Run feeds to the optimization source: it
loads the Candidate by its primary key and fans the Candidate's parameters across every
Component the Candidate was produced from, using the existing component-param slicing.

It is the only Lock-resolution path: the legacy per-Component lock machinery is gone
(ADR-0006, Forward-First — no compat shim).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aegis_runtime import SUPPORTED_ADJUSTMENT_MODES
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType

from research.aegis_research.candidates.identity import (
    CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
)
from research.aegis_research.candidates.store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.component_registry import (
    COMPONENT_FAMILIES,
    ComponentFamily,
)
from research.aegis_research.configuration import LOCK_ROLES, Lock
from research.aegis_research.optimization.component_source import (
    COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION,
)
from research.aegis_research.optimization.param_namespace import (
    ComponentRef,
    slice_by_component,
)

LOCK_RUN_PROVENANCE_SCHEMA_VERSION = "lock_run_provenance.v2"

# ComponentRef -> param-name -> value
ResolvedComponentParams = dict[ComponentRef, dict[str, Any]]


class LockRunResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedLockRun:
    """Every Component's params, drawn from the one Candidate a Lock reproduces."""

    run_id: str
    candidate_key: str
    component_params: ResolvedComponentParams
    provenance: dict[str, Any]
    # The continuous-futures re-basing mode the locked Run's frames were
    # materialised under, parsed from persisted provenance. ``None`` when the Run
    # recorded no mode (no futures, or a Run from before adjustment identity).
    adjustment_mode: ContinuousFutureAdjustmentType | None = None


def resolve_lock_run(lock: Lock, *, store: CandidateStore) -> ResolvedLockRun:
    """Resolve a ``Lock`` to the per-Component params of the Candidate it reproduces.

    ``candidate_id`` is either a representative role keyword (resolved to a
    ``candidate_key`` through ``candidate_rankings``) or a raw ``candidate_key`` hash.
    Either way the loaded Candidate's exact hash is what flows into provenance.
    """
    try:
        candidate_key = _candidate_key_for_lock(lock, store=store)
        row = store.candidate_by_key(candidate_key, run_id=lock.run_id)
    except CandidateStoreError as error:
        raise LockRunResolutionError(
            f"unknown candidate for lock run_id={lock.run_id!r} "
            f"candidate_id={lock.candidate_id!r}: {error}"
        ) from error

    if row["provenance"].get("schema_version") != CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION:
        raise LockRunResolutionError(
            f"candidate {row['candidate_key']} uses unsupported store provenance"
        )
    runtimes = _candidate_component_runtimes(lock, row["provenance"])
    # Lock-run reads the runtime-provenance shape that component_source writes —
    # the one accepted coupling cost (ADR-0006). The contract is version-checked
    # above and every field read strictly below, so a shape that moved fails loudly
    # instead of resolving to different params.
    candidate_slices = slice_by_component(row["params"])
    component_params: ResolvedComponentParams = {}
    for runtime in runtimes:
        family = _component_family(runtime["family"])
        component_id = str(runtime["id"])
        component_slot = str(runtime["slot"])
        params = _component_params_for_runtime(
            component_family=family,
            component_id=component_id,
            component_slot=component_slot,
            component_slices=candidate_slices,
            runtime=runtime,
            candidate_key=row["candidate_key"],
        )
        component_params[ComponentRef(family, component_id, component_slot)] = params

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
        adjustment_mode=_recorded_adjustment_mode(row["provenance"], row["candidate_key"]),
    )


def _recorded_adjustment_mode(
    provenance: Mapping[str, Any],
    candidate_key: str,
) -> ContinuousFutureAdjustmentType | None:
    """Parse the persisted materialisation mode into the typed lock-resolved fact.

    This is the single persisted-provenance read; export consumes only the parsed
    enum and never traverses raw Candidate provenance.
    """
    data = provenance.get("data")
    value = data.get("adjustment_mode") if isinstance(data, Mapping) else None
    if value is None:
        return None
    for mode in SUPPORTED_ADJUSTMENT_MODES:
        if value == mode.value:
            return mode
    supported = sorted(mode.value for mode in SUPPORTED_ADJUSTMENT_MODES)
    raise LockRunResolutionError(
        f"candidate {candidate_key} records unknown adjustment mode {value!r}; "
        f"expected one of {supported}"
    )


def _component_params_for_runtime(
    *,
    component_family: ComponentFamily,
    component_id: str,
    component_slot: str,
    component_slices: Mapping[ComponentRef, Mapping[str, Any]],
    runtime: Mapping[str, Any],
    candidate_key: str,
) -> dict[str, Any]:
    fixed_params = _required_runtime_field(runtime, "fixed_params", candidate_key)
    param_keys = _required_runtime_field(runtime, "param_keys", candidate_key)
    params = dict(fixed_params)
    slice_key = ComponentRef(component_family, component_id, component_slot)
    params.update(component_slices.get(slice_key, {}))
    missing = sorted(set(param_keys) - set(params))
    if missing:
        raise LockRunResolutionError(
            f"candidate {candidate_key} is missing params for component "
            f"{component_family}/{component_id} slot {component_slot!r}: {missing}"
        )
    return params


def _required_runtime_field(
    runtime: Mapping[str, Any],
    field: str,
    candidate_key: str,
) -> Mapping[str, Any]:
    """Read one Component-runtime param mapping, refusing to default it away.

    Defaulting a missing ``fixed_params``/``param_keys`` to ``{}`` would drop the
    Component's fixed params and reproduce a different strategy than the Candidate
    names, with every other guard green — so an absent field is a resolution failure,
    not an empty mapping. The declared contract version already matched by here, so
    this is a shape that disagrees with the version it claims.
    """
    value = runtime.get(field)
    if not isinstance(value, Mapping):
        raise LockRunResolutionError(
            f"candidate {candidate_key} declares component source contract "
            f"{COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION!r} but records a Component "
            f"runtime whose {field!r} is missing or is not a mapping. Its recorded "
            "Component params cannot be reproduced — re-run the optimization under the "
            "current research code, then re-lock."
        )
    return value


def _candidate_key_for_lock(lock: Lock, *, store: CandidateStore) -> str:
    """Resolve a Lock's ``candidate_id`` to a concrete ``candidate_key``.

    A role keyword resolves through ``candidate_rankings``; a raw hash passes through.
    """
    if lock.candidate_id in LOCK_ROLES:
        return store.candidate_key_for_role(lock.run_id, lock.candidate_id)
    return lock.candidate_id


def _assert_every_slice_resolved(
    lock: Lock,
    candidate_slices: Mapping[ComponentRef, Mapping[str, Any]],
    component_params: ResolvedComponentParams,
) -> None:
    orphaned = sorted(
        set(candidate_slices) - set(component_params),
        key=lambda r: (r.family, r.component_id, r.slot),
    )
    if orphaned:
        ref = orphaned[0]
        family, component_id, component_slot = ref.family, ref.component_id, ref.slot
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
    recorded = source.get("schema_version")
    if recorded != COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION:
        # Never navigate a shape this code did not write: the runtime fields below are
        # read by name, so a superseded contract would resolve to different params
        # rather than fail (the store validates its own provenance version, but never
        # this nested one).
        raise LockRunResolutionError(
            f"candidate {lock.candidate_id!r} records component source contract "
            f"{recorded!r}, but this code writes "
            f"{COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION!r}. Its recorded Component "
            "params cannot be reproduced under the current contract — re-run the "
            "optimization under the current research code, then re-lock."
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

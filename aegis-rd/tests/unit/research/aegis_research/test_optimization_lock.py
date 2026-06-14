"""ADR-0006 teardown guard: the legacy per-Component lock machinery is gone.

A Lock now means exactly one thing — the top-level ``lock: {run_id, candidate_id}``.
The per-Component lock-token minting/resolution module and its optimization-package
re-exports were removed (Forward-First, no compat shim).
"""

from __future__ import annotations

import importlib

import pytest

import research.aegis_research.optimization as optimization


def test_legacy_lock_resolution_module_is_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("research.aegis_research.optimization.lock_resolution")


def test_optimization_package_drops_legacy_lock_exports() -> None:
    removed = (
        "ComponentLockRef",
        "ResolvedLock",
        "LockResolutionError",
        "build_component_lock_records",
        "resolve_component_lock",
        "resolve_component_locks",
        "component_lock_token_bytes",
    )
    for name in removed:
        assert name not in optimization.__all__
        assert not hasattr(optimization, name)

"""Standalone gate for aegis-runtime.

ADR-0001 requires an Execution Bundle (and the runtime it depends on) to resolve
WITHOUT aegis-rd — the research apparatus (optimizer, Candidate Store, preflight,
ranking, run pipeline) must stay out of the live path. This test runs in the
runtime's own venv, which carries only the runtime's declared dependencies, so a
successful import already proves the package does not reach back into the
research package; the explicit check below is the contract itself.

The contract is "no research apparatus", not "no dependencies" — the venv also
carries nautilus_trader, numba, pyarrow and pydantic. Only the sys.modules sweep
below decides whether the boundary holds.
"""

from __future__ import annotations

import sys

import aegis_runtime


def test_public_surface_imports_standalone() -> None:
    for name in aegis_runtime.__all__:
        assert hasattr(aegis_runtime, name), f"missing public export: {name}"


def test_runtime_does_not_pull_in_research_package() -> None:
    leaked = sorted(
        m
        for m in sys.modules
        if m == "research"
        or m.startswith("research.")
        or m.startswith("aegis_research")
    )
    assert leaked == [], f"runtime leaked research imports: {leaked}"

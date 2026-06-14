"""Standalone gate for aegis-runtime.

ADR-0001 requires an Execution Bundle (and the runtime it depends on) to resolve
WITHOUT aegis-rd — the research apparatus (optimizer, Candidate Store, preflight,
ranking, run pipeline) must stay out of the live path. This test runs in the
runtime's own venv, which has only numpy + pandas installed, so a successful
import already proves the package does not reach back into the research package;
the explicit checks below document that contract.
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
        if m == "research" or m.startswith("research.") or m.startswith("aegis_research")
    )
    assert leaked == [], f"runtime leaked research imports: {leaked}"

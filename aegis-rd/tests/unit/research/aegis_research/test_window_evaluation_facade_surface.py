from __future__ import annotations

import importlib

from research.aegis_research.optimization import window_evaluation as facade

# The frozen public surface of Window Evaluation (ADR-0026): exactly the
# evaluator and the ResolvedBook it is constructed with. Everything else in the
# package is implementation behind an internal seam — the package's own
# mechanics tests cross it deliberately, production code never does. Widening
# or narrowing this surface is an interface decision, not a refactor.
EXPECTED_PUBLIC_NAMES = (
    "ResolvedBook",
    "WindowEvaluator",
)


def test_facade_all_surface_is_unchanged() -> None:
    assert sorted(facade.__all__) == sorted(EXPECTED_PUBLIC_NAMES)


def test_every_public_name_imports_from_the_facade() -> None:
    fresh = importlib.import_module(
        "research.aegis_research.optimization.window_evaluation"
    )
    for name in EXPECTED_PUBLIC_NAMES:
        assert hasattr(fresh, name), f"facade no longer exposes {name!r}"
        assert getattr(fresh, name) is not None

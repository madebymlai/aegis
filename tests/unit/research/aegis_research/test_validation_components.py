from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.components import (
    _validate_component_indicator_refs,
    _validate_component_ref,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_strategy_component,
)


@pytest.fixture
def registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def test_component_ref_accepts_known_strategy(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    definition = _validate_component_ref(
        "strategy", {"id": "demo.strategy"}, "strategies", issues, component_registry=registry
    )
    assert issues == []
    assert definition is not None


def test_component_ref_rejects_unknown_id(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_component_ref(
        "strategy", {"id": "missing.one"}, "strategies", issues, component_registry=registry
    )
    # Singular is derived mechanically as family[:-1] ("strategies" -> "strategie").
    assert ("strategy.id", "unknown strategie component id") in [
        (i.path, i.message) for i in issues
    ]


def test_component_ref_rejects_lock_and_candidate_together(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_component_ref(
        "strategy",
        {"id": "demo.strategy", "lock_id": "L", "candidate_id": "C", "run_id": "R"},
        "strategies",
        issues,
        component_registry=registry,
    )
    assert ("strategy", "lock_id and candidate_id are mutually exclusive") in [
        (i.path, i.message) for i in issues
    ]


def test_indicator_refs_flag_duplicate_component_id(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_component_indicator_refs(
        "indicators",
        [{"id": "demo.returns"}, {"id": "demo.returns"}],
        issues,
        component_registry=registry,
    )
    assert any("duplicates indicator component id" in i.message for i in issues)

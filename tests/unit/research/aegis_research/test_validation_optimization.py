from __future__ import annotations

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.optimization import (
    _validate_optimization,
    _validate_optimization_execute,
    _validate_optimization_random_policy,
)


def test_optimization_requires_search_policy() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_optimization({"optimization": {"split": {}}}, issues)
    assert ("optimization.search", "is required") in [(i.path, i.message) for i in issues]


def test_execute_rejects_reserved_key() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_optimization_execute({"seed": 1}, issues)
    assert any(i.path == "optimization.execute" and "reserved keys" in i.message for i in issues)


def test_random_search_requires_subset_and_seed() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_optimization_random_policy({}, issues, search="random")
    paths = {i.path for i in issues}
    assert "optimization.random_subset" in paths
    assert "optimization.seed" in paths


def test_grid_search_rejects_random_subset() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_optimization_random_policy({"random_subset": 10}, issues, search="grid")
    assert ("optimization.random_subset", "only valid when optimization.search is 'random'") in [
        (i.path, i.message) for i in issues
    ]

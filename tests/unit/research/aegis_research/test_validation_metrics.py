from __future__ import annotations

import pytest

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.metrics import _validate_ranking
from research.aegis_research.metrics import freeze_metric_registry, make_default_metric_registry


@pytest.fixture
def registry():
    return freeze_metric_registry(make_default_metric_registry())


def _valid_metric(registry) -> str:
    return sorted(registry.ids())[0]


def test_ranking_accepts_known_metric(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_ranking("ranking", {"metric": _valid_metric(registry)}, issues, registry=registry)
    assert issues == []


def test_ranking_flags_unknown_key(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_ranking(
        "ranking",
        {"metric": _valid_metric(registry), "bogus": 1},
        issues,
        registry=registry,
    )
    assert "ranking.bogus" in {issue.path for issue in issues}


def test_ranking_rejects_min_weight_out_of_range(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_ranking(
        "ranking",
        {"metric": _valid_metric(registry), "min_weight": 1.5},
        issues,
        registry=registry,
    )
    assert [(i.path, i.message) for i in issues] == [
        ("ranking.min_weight", "must be a number between 0.0 and 1.0")
    ]


def test_ranking_rejects_negative_min_trades(registry) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_ranking(
        "ranking",
        {"metric": _valid_metric(registry), "min_trades": -1},
        issues,
        registry=registry,
    )
    assert [(i.path, i.message) for i in issues] == [
        ("ranking.min_trades", "must be a non-negative integer")
    ]

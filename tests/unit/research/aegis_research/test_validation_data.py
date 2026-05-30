from __future__ import annotations

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.data import (
    _is_absolute_or_user_path,
    _validate_data,
)


def test_validate_data_accepts_minimal_synthetic_source() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_data({"source": "synthetic", "arrays": ["OHLCV"]}, issues)
    assert issues == []


def test_validate_data_requires_arrays() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_data({"source": "synthetic"}, issues)
    assert ("data.arrays", "is required") in [(i.path, i.message) for i in issues]


def test_validate_data_rejects_unknown_source() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_data({"source": "nope", "arrays": ["OHLCV"]}, issues)
    assert "data.source" in {i.path for i in issues}


def test_is_absolute_or_user_path_classifies_paths() -> None:
    assert _is_absolute_or_user_path("/etc/passwd") is True
    assert _is_absolute_or_user_path("~/secrets") is True
    assert _is_absolute_or_user_path("data/prices.csv") is False

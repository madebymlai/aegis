from __future__ import annotations

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.base import (
    _require_int,
    _validate_json_like,
    _validate_known_keys,
)


def test_validate_known_keys_flags_unknown_top_level_field() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_known_keys("$", {"name": "x", "bogus": 1}, {"name"}, issues)
    assert [issue.path for issue in issues] == ["bogus"]


def test_require_int_flags_missing_required_field() -> None:
    issues: list[ConfigValidationIssue] = []
    _require_int("schema_version", {}, issues, positive=True)
    assert [(issue.path, issue.message) for issue in issues] == [("schema_version", "is required")]


def test_validate_json_like_rejects_non_finite_number() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_json_like("data.seed", float("inf"), issues)
    assert [issue.message for issue in issues] == ["must be finite"]

from __future__ import annotations

from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    PORTFOLIO_DIRECTIONS,
    ConfigValidationIssue,
)
from research.aegis_research.configuration.validation.portfolio import (
    _validate_portfolio,
    _validate_report,
)


def test_schema_version_is_seven() -> None:
    assert CONFIG_SCHEMA_VERSION == 7


def test_portfolio_directions_admit_signed_book() -> None:
    assert PORTFOLIO_DIRECTIONS == {"longonly", "shortonly", "both"}


def test_portfolio_requires_gross_cap() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({}, issues)
    assert ("portfolio.gross_cap", "is required") in [(i.path, i.message) for i in issues]


def test_portfolio_accepts_gross_cap_above_one_no_ceiling() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 2.0}, issues)
    assert [i for i in issues if i.path == "portfolio.gross_cap"] == []


def test_portfolio_rejects_non_positive_gross_cap() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 0.0}, issues)
    assert [i.path for i in issues if i.path == "portfolio.gross_cap"] == ["portfolio.gross_cap"]


def test_portfolio_accepts_net_cap() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 2.0, "net_cap": 0.0}, issues)
    assert [i for i in issues if i.path == "portfolio.net_cap"] == []


def test_portfolio_rejects_removed_target_exposure_cap_with_clear_message() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 1.0, "target_exposure_cap": 1.0}, issues)
    messages = [i.message for i in issues if i.path == "portfolio.target_exposure_cap"]
    assert messages, "target_exposure_cap must be rejected"
    assert "gross_cap" in messages[0]


def test_portfolio_admits_direction_both() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 2.0, "direction": "both"}, issues)
    assert [i for i in issues if i.path == "portfolio.direction"] == []


def test_portfolio_admits_direction_shortonly() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 2.0, "direction": "shortonly"}, issues)
    assert [i for i in issues if i.path == "portfolio.direction"] == []


def test_portfolio_rejects_unknown_direction() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 1.0, "direction": "sideways"}, issues)
    assert [i.path for i in issues if i.path == "portfolio.direction"] == ["portfolio.direction"]


def test_report_rejects_out_of_range_drawdown() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_report({"max_oos_drawdown": 2.0}, issues)
    assert ("report.max_oos_drawdown", "must be at most 1") in [(i.path, i.message) for i in issues]

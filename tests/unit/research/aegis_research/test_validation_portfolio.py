from __future__ import annotations

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.portfolio import (
    _validate_portfolio,
    _validate_report,
)


def test_portfolio_requires_target_exposure_cap() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({}, issues)
    assert ("portfolio.target_exposure_cap", "is required") in [(i.path, i.message) for i in issues]


def test_portfolio_rejects_target_exposure_cap_above_one() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"target_exposure_cap": 1.5}, issues)
    assert ("portfolio.target_exposure_cap", "must be at most 1") in [
        (i.path, i.message) for i in issues
    ]


def test_portfolio_rejects_non_longonly_direction() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"target_exposure_cap": 0.5, "direction": "both"}, issues)
    assert ("portfolio.direction", "v1 strategy signal contract is long-only; use longonly") in [
        (i.path, i.message) for i in issues
    ]


def test_report_rejects_out_of_range_drawdown() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_report({"max_oos_drawdown": 2.0}, issues)
    assert ("report.max_oos_drawdown", "must be at most 1") in [(i.path, i.message) for i in issues]

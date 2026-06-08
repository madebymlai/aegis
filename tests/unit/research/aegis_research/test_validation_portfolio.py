from __future__ import annotations

from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    PORTFOLIO_DIRECTIONS,
    ConfigValidationIssue,
    PortfolioConfig,
    ReportConfig,
)
from research.aegis_research.configuration.validation.portfolio import (
    _validate_portfolio,
    _validate_report,
)


def test_schema_version_is_eight() -> None:
    assert CONFIG_SCHEMA_VERSION == 8


def test_portfolio_directions_admit_signed_book() -> None:
    assert {"longonly", "shortonly", "both"} == PORTFOLIO_DIRECTIONS


def test_portfolio_requires_gross_cap() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({}, issues)
    assert ("portfolio.gross_cap", "is required") in [(i.path, i.message) for i in issues]


def test_portfolio_requires_direction() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 1.0}, issues)
    assert ("portfolio.direction", "is required") in [(i.path, i.message) for i in issues]


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


def test_report_periods_per_year_shares_metric_annualization_calendar() -> None:
    # Carry annualizes on the same freq/year_freq the Sharpe ratio uses (one calendar):
    # daily defaults give 252, and a weekly book gives 52.
    assert ReportConfig().periods_per_year == 252
    assert ReportConfig(freq="7D", year_freq="364D").periods_per_year == 52


def test_short_financing_rate_defaults_carry_on() -> None:
    # Non-zero borrow default = carry ON by default; rebate defaults to 0.0.
    config = PortfolioConfig(direction="longonly")
    assert config.short_borrow_rate == 0.005
    assert config.short_rebate_rate == 0.0


def test_portfolio_accepts_short_financing_rates() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio(
        {"gross_cap": 2.0, "short_borrow_rate": 0.01, "short_rebate_rate": 0.002},
        issues,
    )
    assert [
        i for i in issues if i.path in {"portfolio.short_borrow_rate", "portfolio.short_rebate_rate"}
    ] == []


def test_portfolio_rejects_negative_short_borrow_rate() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 1.0, "short_borrow_rate": -0.001}, issues)
    assert [i.path for i in issues if i.path == "portfolio.short_borrow_rate"] == [
        "portfolio.short_borrow_rate"
    ]


def test_portfolio_rejects_negative_short_rebate_rate() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio({"gross_cap": 1.0, "short_rebate_rate": -0.001}, issues)
    assert [i.path for i in issues if i.path == "portfolio.short_rebate_rate"] == [
        "portfolio.short_rebate_rate"
    ]


def test_report_rejects_out_of_range_drawdown() -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_report({"max_oos_drawdown": 2.0}, issues)
    assert ("report.max_oos_drawdown", "must be at most 1") in [(i.path, i.message) for i in issues]

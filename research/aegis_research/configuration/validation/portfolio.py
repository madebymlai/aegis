"""Portfolio and Report threshold validation.

Validates the ``portfolio`` block (init cash, fees, slippage, target exposure cap,
long-only direction contract, removed sizing fields) and the ``report`` block (OOS
Sharpe/drawdown/trade thresholds and Timedelta-string frequencies).
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import (
    PORTFOLIO_DIRECTIONS,
    PORTFOLIO_TARGET_SIZE_TYPES,
    ConfigValidationIssue,
)
from research.aegis_research.configuration.validation.base import (
    _optional_int,
    _optional_number,
    _require_timedelta_str,
)

PORTFOLIO_REMOVED_FIELDS: dict[str, str] = {
    "entry_budget": "renamed to portfolio.target_exposure_cap",
}


def _validate_portfolio(portfolio: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_number("portfolio.init_cash", portfolio, issues, positive=True)
    _optional_number("portfolio.fees", portfolio, issues, minimum=0)
    _optional_number("portfolio.slippage", portfolio, issues, minimum=0)
    for removed, message in PORTFOLIO_REMOVED_FIELDS.items():
        if removed in portfolio:
            issues.append(ConfigValidationIssue(f"portfolio.{removed}", message))
    if "target_exposure_cap" not in portfolio:
        issues.append(ConfigValidationIssue("portfolio.target_exposure_cap", "is required"))
    else:
        _optional_number(
            "portfolio.target_exposure_cap", portfolio, issues, positive=True, maximum=1
        )
    if "size" in portfolio:
        issues.append(
            ConfigValidationIssue(
                "portfolio.size",
                "was removed; use portfolio.target_exposure_cap for v1 signal entry sizing",
            )
        )
    if "size_type" in portfolio and not isinstance(portfolio["size_type"], str):
        issues.append(ConfigValidationIssue("portfolio.size_type", "must be a string"))
    elif "size_type" in portfolio:
        if portfolio["size_type"] in PORTFOLIO_TARGET_SIZE_TYPES:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    "target allocation sizing is deferred; baseline signal simulation uses portfolio.target_exposure_cap",
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    "was removed; baseline signal simulation resolves valuepercent sizing internally",
                )
            )
    direction = portfolio.get("direction", "longonly")
    if "direction" in portfolio and not isinstance(direction, str):
        issues.append(ConfigValidationIssue("portfolio.direction", "must be a string"))
    elif direction != "longonly":
        if direction in {"both", "shortonly"}:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.direction",
                    "v1 strategy signal contract is long-only; use longonly",
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.direction",
                    f"must be one of {sorted(PORTFOLIO_DIRECTIONS)}",
                )
            )


def _validate_report(report: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_number("report.min_oos_sharpe", report, issues)
    _optional_number("report.max_oos_drawdown", report, issues, minimum=0, maximum=1)
    _optional_int("report.min_oos_trades", report, issues, minimum=0)
    if "freq" in report:
        _require_timedelta_str("report.freq", report, issues)
    if "year_freq" in report:
        _require_timedelta_str("report.year_freq", report, issues)

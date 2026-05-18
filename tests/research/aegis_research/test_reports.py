from __future__ import annotations

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import (
    REPORT_STATUS_NEEDS_MORE_EVIDENCE,
    PortfolioConfig,
    ReportConfig,
    SignalConfig,
)
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.reports import build_survival_report, portfolio_metrics


def test_portfolio_metrics_use_shared_cash_group_scope() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0, 14.0], "B": [20.0, 21.0, 22.0, 23.0, 24.0]},
        index=index,
    )
    entries = pd.DataFrame(
        {"A": [True, False, False, False, False], "B": [True, False, False, False, False]},
        index=index,
    )
    exits = pd.DataFrame(False, index=index, columns=close.columns)
    simulation = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=0.6, fees=0, slippage=0),
        SignalConfig(execution_timing="same_close"),
    )

    metrics = portfolio_metrics(simulation.portfolio, ReportConfig(freq="1D", year_freq="252D"))

    assert metrics["metric_scope"] == "shared_cash_group"
    assert metrics["metric_assumptions"] == {
        "scope": "shared_cash_group",
        "scope_detail": "one shared cash group across configured symbols",
        "freq": "1D",
        "year_freq": "252D",
        "benchmark_status": "none",
        "benchmark_source": None,
    }
    assert metrics["total_return_pct"] == pytest.approx(18.0)
    assert metrics["per_symbol"]["total_return_pct"]["A"] == pytest.approx(12.0)
    assert metrics["per_symbol"]["total_return_pct"]["B"] == pytest.approx(6.0)


def test_portfolio_metrics_fail_fast_without_single_shared_cash_group() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0], "B": [20.0, 21.0, 22.0]}, index=index)
    entries = pd.DataFrame({"A": [True, False, False], "B": [True, False, False]}, index=index)
    exits = pd.DataFrame(False, index=index, columns=close.columns)
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        init_cash=10_000,
        size=0.5,
        size_type="valuepercent",
        fees=0,
        slippage=0,
    )

    with pytest.raises(ValueError, match="exactly one group"):
        portfolio_metrics(pf, ReportConfig())


def test_non_decision_grade_validation_cannot_survive_by_metrics() -> None:
    report = build_survival_report(
        "diagnostic-run",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
        validation_metadata={"decision_grade": False},
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "non-decision-grade" in report["reasons"][0]


def test_missing_validation_metadata_cannot_survive_by_metrics() -> None:
    report = build_survival_report(
        "missing-validation-metadata",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "non-decision-grade" in report["reasons"][0]


def test_label_purging_report_requires_split_evidence_even_when_metrics_pass() -> None:
    report = build_survival_report(
        "missing-split-evidence",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
        validation_metadata={
            "decision_grade": True,
            "target": {"split_safety": {"purging_required": True}},
            "split_metadata": {},
        },
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "split evidence" in report["reasons"][0]


def _passing_metrics() -> dict[str, float | int]:
    return {
        "sharpe_ratio": 1.0,
        "max_drawdown_pct": 10.0,
        "total_trades": 10,
    }

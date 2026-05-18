from __future__ import annotations

import warnings
from typing import ClassVar

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import (
    REPORT_STATUS_NEEDS_MORE_EVIDENCE,
    REPORT_STATUS_REJECTED,
    REPORT_STATUS_SURVIVED,
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
    assert metrics["metric_roles"]["total_return_pct"]["required_gate_input"] is False
    assert metrics["metric_roles"]["sharpe_ratio"]["required_gate_input"] is True
    assert metrics["metric_evidence"]["total_return_pct"]["source"]["identity"] == "total_return"
    assert metrics["metric_evidence"]["sharpe_ratio"]["settings"]["year_freq"] == "252D"
    assert metrics["metric_evidence"]["max_drawdown_pct"]["unit"] == ("percent_loss_magnitude")
    assert set(metrics["optional_diagnostics"]) == {
        "probabilistic_sharpe_ratio",
        "deflated_sharpe_ratio",
    }
    assert metrics["per_symbol_metric_evidence"]["total_return_pct"]["A"]["availability"] == (
        "available"
    )


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


def test_portfolio_metrics_records_warning_and_non_finite_evidence() -> None:
    warning_metrics = portfolio_metrics(
        _FakePortfolio(sharpe_ratio=1.2, warning_message="Sharpe Ratio requires frequency"),
        ReportConfig(freq="1D", year_freq="252D"),
    )
    infinite_metrics = portfolio_metrics(
        _FakePortfolio(sharpe_ratio=float("inf")),
        ReportConfig(freq="1D", year_freq="252D"),
    )

    assert warning_metrics["sharpe_ratio"] is None
    assert warning_metrics["metric_evidence"]["sharpe_ratio"]["availability"] == (
        "unavailable_metric"
    )
    assert warning_metrics["metric_evidence"]["sharpe_ratio"]["non_finite"] == "metric_warning"
    assert warning_metrics["metric_evidence"]["sharpe_ratio"]["warnings"][0]["category"] == (
        "RuntimeWarning"
    )
    assert infinite_metrics["sharpe_ratio"] is None
    assert infinite_metrics["metric_evidence"]["sharpe_ratio"]["non_finite"] == (
        "positive_infinity"
    )


def test_non_decision_grade_validation_cannot_survive_by_metrics() -> None:
    report = build_survival_report(
        "diagnostic-run",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=0.0, max_drawdown_pct=50.0, total_trades=0),
        ],
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
        split_metric_evidence=[],
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "non-decision-grade" in report["reasons"][0]


def test_label_purging_report_requires_split_evidence_even_when_metrics_pass() -> None:
    report = build_survival_report(
        "missing-split-evidence",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
        split_metric_evidence=[],
        validation_metadata={
            "decision_grade": True,
            "target": {"split_safety": {"purging_required": True}},
            "split_metadata": {},
        },
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "split evidence" in report["reasons"][0]


def test_split_first_gates_can_survive_with_passing_split_evidence() -> None:
    report = build_survival_report(
        "passing-splits",
        train_metrics=_passing_metrics(),
        test_metrics={"sharpe_ratio": -10.0, "max_drawdown_pct": 99.0, "total_trades": 0},
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=10),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=1.1, max_drawdown_pct=10.0, total_trades=4),
            _split_row("split_1", sharpe_ratio=1.2, max_drawdown_pct=15.0, total_trades=6),
        ],
    )

    assert report["status"] == REPORT_STATUS_SURVIVED
    assert report["metric_roles"]["test_metrics"] == "descriptive_summary"
    assert report["decision_policy"]["metrics"]["sharpe_ratio"]["policy"] == "all_splits_pass"
    assert report["decision_policy"]["metrics"]["total_trades"]["policy"] == (
        "sum_across_test_splits"
    )
    assert (
        report["metric_evidence_summary"]["metrics"]["sharpe_ratio"]["required_gate_input"] is True
    )


def test_split_first_gates_reject_when_aggregate_passes_but_split_fails() -> None:
    report = build_survival_report(
        "failed-split",
        train_metrics=_passing_metrics(),
        test_metrics={"sharpe_ratio": 2.0, "max_drawdown_pct": 5.0, "total_trades": 99},
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=10),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=1.2, max_drawdown_pct=10.0, total_trades=5),
            _split_row("split_1", sharpe_ratio=0.5, max_drawdown_pct=15.0, total_trades=5),
        ],
    )

    assert report["status"] == REPORT_STATUS_REJECTED
    assert any(gate["status"] == "fail" for gate in report["gate_outcomes"])
    assert "split_1" in " ".join(report["reasons"])


def test_mixed_required_failure_and_unavailable_metric_rejects() -> None:
    report = build_survival_report(
        "mixed-failure-and-gap",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=10),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=0.5, max_drawdown_pct=10.0, total_trades=5),
            _split_row("split_1", sharpe_ratio=None, max_drawdown_pct=15.0, total_trades=5),
        ],
    )

    assert report["status"] == REPORT_STATUS_REJECTED
    statuses = {gate["status"] for gate in report["gate_outcomes"]}
    assert {"fail", "unavailable_metric"} <= statuses


def test_unavailable_required_metric_without_failure_needs_more_evidence() -> None:
    report = build_survival_report(
        "unavailable-sharpe",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=10),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=None, max_drawdown_pct=10.0, total_trades=10),
        ],
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert any(gate["status"] == "unavailable_metric" for gate in report["gate_outcomes"])


def test_gate_uses_metric_evidence_availability_over_scalar_value() -> None:
    report = build_survival_report(
        "evidence-unavailable",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=1),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row(
                "split_0",
                sharpe_ratio=2.0,
                max_drawdown_pct=10.0,
                total_trades=1,
                sharpe_availability="unavailable_metric",
                sharpe_warnings=[{"category": "RuntimeWarning", "message": "requires frequency"}],
            ),
        ],
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    sharpe_gate = next(gate for gate in report["gate_outcomes"] if gate["name"] == "oos_sharpe")
    assert sharpe_gate["status"] == "unavailable_metric"
    assert sharpe_gate["evidence"]["warnings"][0]["message"] == "requires frequency"


def test_malformed_split_metric_evidence_fails_fast() -> None:
    with pytest.raises(TypeError, match="metric_evidence"):
        build_survival_report(
            "malformed-evidence",
            train_metrics=_passing_metrics(),
            test_metrics=_passing_metrics(),
            config=ReportConfig(),
            validation_metadata={"decision_grade": True},
            split_metric_evidence=[
                {"split": "split_0", "set": "test", "metrics": _passing_metrics()}
            ],
        )


def test_total_trades_gate_uses_sum_and_low_total_is_inconclusive() -> None:
    report = build_survival_report(
        "too-few-trades",
        train_metrics=_passing_metrics(),
        test_metrics={"sharpe_ratio": 2.0, "max_drawdown_pct": 5.0, "total_trades": 99},
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=10),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=1.2, max_drawdown_pct=10.0, total_trades=4),
            _split_row("split_1", sharpe_ratio=1.2, max_drawdown_pct=10.0, total_trades=5),
        ],
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    trade_gate = next(gate for gate in report["gate_outcomes"] if gate["name"] == "oos_trades")
    assert trade_gate["actual_value"] == 9.0
    assert trade_gate["status"] == "insufficient_evidence"
    assert trade_gate["inputs"][0]["split"] == "split_0"


def test_drawdown_gate_compares_loss_magnitude() -> None:
    report = build_survival_report(
        "negative-drawdown",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=1),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio=1.2, max_drawdown_pct=-35.0, total_trades=1),
        ],
    )

    assert report["status"] == REPORT_STATUS_REJECTED
    drawdown_gate = next(gate for gate in report["gate_outcomes"] if gate["name"] == "oos_drawdown")
    assert drawdown_gate["actual_value"] == 35.0
    assert drawdown_gate["status"] == "fail"


def test_string_nan_gate_metric_is_unavailable() -> None:
    report = build_survival_report(
        "string-nan",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(min_oos_sharpe=1.0, max_oos_drawdown=0.2, min_oos_trades=1),
        validation_metadata={"decision_grade": True},
        split_metric_evidence=[
            _split_row("split_0", sharpe_ratio="NaN", max_drawdown_pct="NaN", total_trades=1),
        ],
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    statuses = {
        gate["name"]: gate["status"]
        for gate in report["gate_outcomes"]
        if gate["name"] in {"oos_sharpe", "oos_drawdown"}
    }
    assert statuses == {"oos_sharpe": "unavailable_metric", "oos_drawdown": "unavailable_metric"}


def _passing_metrics() -> dict[str, float | int]:
    return {
        "sharpe_ratio": 1.0,
        "max_drawdown_pct": 10.0,
        "total_trades": 10,
    }


def _split_row(
    split: str,
    *,
    sharpe_ratio: object,
    max_drawdown_pct: object,
    total_trades: object,
    sharpe_availability: str | None = None,
    sharpe_warnings: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    metrics = {
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "total_trades": total_trades,
    }
    return {
        "split": split,
        "set": "test",
        "metric_assumptions": {"benchmark_status": "none", "freq": "1D", "year_freq": "252D"},
        "metrics": metrics,
        "metric_evidence": {
            "sharpe_ratio": _evidence(
                "sharpe_ratio",
                sharpe_ratio,
                availability=sharpe_availability,
                warnings=sharpe_warnings,
            ),
            "max_drawdown_pct": _evidence("max_drawdown_pct", max_drawdown_pct),
            "total_trades": _evidence("total_trades", total_trades),
        },
        "optional_diagnostics": {},
    }


def _evidence(
    name: str,
    value: object,
    *,
    availability: str | None = None,
    warnings: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    availability = availability or ("unavailable_metric" if value is None else "available")
    return {
        "name": name,
        "value": value if availability == "available" else None,
        "raw_value": value if availability == "available" else None,
        "normalized_value": value if availability == "available" else None,
        "availability": availability,
        "non_finite": None if availability == "available" else "missing",
        "unit": "percent_loss_magnitude" if name == "max_drawdown_pct" else "ratio",
        "source": {"engine": "vectorbtpro", "identity": name, "method": "test"},
        "settings": {"freq": "1D", "year_freq": "252D"},
        "warnings": warnings or [],
        "required_report_output": True,
        "required_gate_input": name in {"sharpe_ratio", "max_drawdown_pct", "total_trades"},
    }


class _FakePortfolio:
    metrics: ClassVar[dict[str, dict[str, str]]] = {
        "total_return": {"title": "Total Return [%]"},
        "max_dd": {"title": "Max Drawdown [%]"},
        "total_trades": {"title": "Total Trades"},
        "win_rate": {"title": "Win Rate [%]"},
        "total_fees_paid": {"title": "Total Fees Paid"},
        "sharpe_ratio": {"title": "Sharpe Ratio"},
    }

    def __init__(self, *, sharpe_ratio: float, warning_message: str | None = None) -> None:
        self.sharpe_ratio = sharpe_ratio
        self.warning_message = warning_message

    def stats(self, *, group_by=None, **kwargs):
        column = "SYN" if group_by is False else "portfolio"
        return pd.DataFrame(
            {column: [1.0, 10.0, 1.0, 50.0, 0.0]},
            index=[
                "Total Return [%]",
                "Max Drawdown [%]",
                "Total Trades",
                "Win Rate [%]",
                "Total Fees Paid",
            ],
        )

    def get_sharpe_ratio(self, *, group_by=None, **kwargs):
        if self.warning_message:
            warnings.warn(self.warning_message, RuntimeWarning, stacklevel=2)
        if group_by is False:
            return pd.Series({"SYN": self.sharpe_ratio})
        return self.sharpe_ratio

from __future__ import annotations

import warnings
from typing import ClassVar

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import (
    PortfolioConfig,
    ReportConfig,
    SignalConfig,
)
from research.aegis_research.portfolios import simulate_portfolio, simulate_portfolio_batch
from research.aegis_research.reports import (
    portfolio_metrics,
    portfolio_metrics_by_candidate_group,
)


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
    assert metrics["total_return"] == pytest.approx(18.0)
    assert metrics["per_symbol"]["total_return"]["A"] == pytest.approx(12.0)
    assert metrics["per_symbol"]["total_return"]["B"] == pytest.approx(6.0)
    assert metrics["metric_roles"]["total_return"]["required_gate_input"] is False
    assert metrics["metric_roles"]["sharpe_ratio"]["required_gate_input"] is True
    assert metrics["metric_evidence"]["total_return"]["source"]["identity"] == "total_return"
    assert metrics["metric_evidence"]["sharpe_ratio"]["settings"]["year_freq"] == "252D"
    assert metrics["metric_evidence"]["max_dd"]["unit"] == ("percent_loss_magnitude")
    assert set(metrics["optional_diagnostics"]) == {
        "probabilistic_sharpe_ratio",
        "deflated_sharpe_ratio",
    }
    assert metrics["per_symbol_metric_evidence"]["total_return"]["A"]["availability"] == (
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


def test_portfolio_metrics_by_candidate_group_preserves_candidate_scope() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0, 14.0], "B": [20.0, 21.0, 22.0, 23.0, 24.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["candidate-a", "candidate-b"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    entries = pd.DataFrame(False, index=index, columns=columns)
    entries.loc[index[0], :] = True
    exits = pd.DataFrame(False, index=index, columns=columns)
    simulation = simulate_portfolio_batch(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=0.6, fees=0, slippage=0),
        SignalConfig(execution_timing="same_close"),
    )

    metrics = portfolio_metrics_by_candidate_group(
        simulation.portfolio,
        ReportConfig(freq="1D", year_freq="252D"),
        ["candidate-a", "candidate-b"],
    )

    assert set(metrics) == {"candidate-a", "candidate-b"}
    assert metrics["candidate-a"]["total_return"] == pytest.approx(18.0)
    assert metrics["candidate-b"]["total_return"] == pytest.approx(18.0)
    assert metrics["candidate-a"]["per_symbol"]["total_return"] == {
        "A": pytest.approx(12.0),
        "B": pytest.approx(6.0),
    }
    assert metrics["candidate-a"]["metric_assumptions"]["scope_detail"] == (
        "one shared cash group across symbols for each candidate"
    )
    assert set(metrics["candidate-a"]["optional_diagnostics"]) == {
        "probabilistic_sharpe_ratio",
        "deflated_sharpe_ratio",
    }


def test_portfolio_metrics_by_candidate_group_handles_single_candidate_batch() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0, 14.0], "B": [20.0, 21.0, 22.0, 23.0, 24.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["candidate-a"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    entries = pd.DataFrame(False, index=index, columns=columns)
    entries.loc[index[0], :] = True
    exits = pd.DataFrame(False, index=index, columns=columns)
    simulation = simulate_portfolio_batch(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=0.6, fees=0, slippage=0),
        SignalConfig(execution_timing="same_close"),
    )

    metrics = portfolio_metrics_by_candidate_group(
        simulation.portfolio,
        ReportConfig(freq="1D", year_freq="252D"),
        ["candidate-a"],
    )

    assert metrics["candidate-a"]["total_return"] == pytest.approx(18.0)


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

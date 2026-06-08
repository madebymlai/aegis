from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.accessors import (
    METRIC_INDEX_NAME,
    central_metrics_from_accessors,
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.portfolios import simulate_portfolio_batch
from tests.support.research.aegis_research.metric_oracle import (
    report_grade_metrics,
    report_grade_metrics_by_candidate,
)


def _build_portfolio() -> Any:
    """Build a minimal VBT portfolio with known trades for testing."""
    index = pd.date_range("2024-01-01", periods=30, freq="D")
    close = pd.DataFrame(
        {"A": 100 + np.cumsum(np.random.default_rng(42).normal(0, 1, 30))},
        index=index,
    )
    entries = pd.DataFrame({"A": False}, index=index)
    exits = pd.DataFrame({"A": False}, index=index)
    entries.iloc[0] = True
    exits.iloc[5] = True
    entries.iloc[10] = True
    exits.iloc[15] = True
    entries.iloc[20] = True
    exits.iloc[25] = True
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        fees=0.001,
        init_cash=10_000,
    )
    return pf


def _assert_metric_parity(actual: Any, expected: float | None, *, metric_name: str) -> None:
    if expected is None:
        assert actual is None or pd.isna(actual), (
            f"{metric_name}: expected unavailable, got {actual}"
        )
    else:
        assert actual == pytest.approx(expected, rel=1e-6), (
            f"{metric_name}: production={actual} vs oracle={expected}"
        )


def test_returns_series_with_all_central_metric_keys() -> None:
    pf = _build_portfolio()
    config = ReportConfig()

    result = central_metrics_from_accessors(pf, config)

    assert isinstance(result, pd.Series)
    assert result.name == "value"
    assert result.index.name == METRIC_INDEX_NAME
    assert set(result.index) == set(PORTFOLIO_METRIC_VALUE_KEYS)


def test_parity_with_report_grade_oracle_for_finite_portfolio() -> None:
    pf = _build_portfolio()
    config = ReportConfig()

    lightweight = central_metrics_from_accessors(pf, config)
    oracle = report_grade_metrics(pf, config)

    for metric_name in PORTFOLIO_METRIC_VALUE_KEYS:
        _assert_metric_parity(
            lightweight[metric_name], oracle[metric_name], metric_name=metric_name
        )


def test_grouped_sweep_path_parity_with_report_grade_oracle() -> None:
    """Pin the path the optimization sweep actually runs.

    ``central_metrics_from_grouped_accessors`` assigns per-group accessor values
    to candidate keys positionally. Distinct per-candidate allocations make a
    mis-ordering observable: the report-grade oracle resolves the same values by
    candidate label through ``pf.stats()``.
    """
    # A price path that peaks then falls, so drawdown is a real value both VBT
    # surfaces agree on (a monotonically rising path leaves only noise-floor
    # drawdown, which pf.stats() and get_max_drawdown() report differently).
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame(
        {
            "A": [10.0, 12.0, 15.0, 11.0, 9.0, 12.0, 14.0, 13.0],
            "B": [20.0, 23.0, 27.0, 30.0, 22.0, 18.0, 24.0, 26.0],
        },
        index=index,
    )
    candidate_ids = ["candidate-a", "candidate-b"]
    columns = pd.MultiIndex.from_product(
        [candidate_ids, ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("candidate-a", slice(None))] = 0.3
    # candidate-b at 0.5 each is gross 1.0 — distinct from candidate-a yet within the default
    # exposure caps, so the gate admits this metrics-parity fixture at leverage 1.0.
    allocations.loc[index[0], ("candidate-b", slice(None))] = 0.5
    simulation = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0.001, slippage=0, direction="longonly")
    )
    config = ReportConfig(freq="1D", year_freq="252D")

    candidate_keys = [(candidate_id,) for candidate_id in candidate_ids]
    production = central_metrics_from_grouped_accessors(
        simulation.portfolio, config, candidate_keys, ["candidate_id"]
    )
    oracle = report_grade_metrics_by_candidate(simulation.portfolio, config, candidate_ids)

    assert list(production.index) == candidate_keys
    for candidate_id in candidate_ids:
        production_row = production.loc[(candidate_id,)]
        for metric_name in PORTFOLIO_METRIC_VALUE_KEYS:
            _assert_metric_parity(
                production_row[metric_name],
                oracle[candidate_id][metric_name],
                metric_name=f"{candidate_id}/{metric_name}",
            )


def test_non_finite_values_normalize_to_none() -> None:
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.DataFrame({"A": [100.0] * 10}, index=index)
    pf = vbt.Portfolio.from_signals(
        close,
        entries=pd.DataFrame({"A": [False] * 10}, index=index),
        exits=pd.DataFrame({"A": [False] * 10}, index=index),
        fees=0.0,
        init_cash=10_000,
    )
    config = ReportConfig()

    result = central_metrics_from_accessors(pf, config)

    assert result["total_return"] == pytest.approx(0.0)
    assert result["max_dd"] == pytest.approx(0.0)
    assert result["total_trades"] == pytest.approx(0.0)
    assert pd.isna(result["win_rate"]), "win_rate should be NaN when no trades"
    assert result["total_fees_paid"] == pytest.approx(0.0)
    assert pd.isna(result["sharpe_ratio"]), "sharpe_ratio should be NaN for flat returns"

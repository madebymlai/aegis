from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.accessors import (
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.portfolios import simulate_portfolio_batch
from tests.support.research.aegis_research.metric_oracle import (
    report_grade_metrics_by_candidate,
)


def _assert_metric_parity(actual: Any, expected: float | None, *, metric_name: str) -> None:
    if expected is None:
        assert actual is None or pd.isna(actual), (
            f"{metric_name}: expected unavailable, got {actual}"
        )
    else:
        assert actual == pytest.approx(expected, rel=1e-6), (
            f"{metric_name}: production={actual} vs oracle={expected}"
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
    """The grouped path normalises non-finite metric values (NaN/inf) to None.

    A flat-price candidate with no closed trades has an undefined win rate and
    Sharpe (NaN); the registry-driven loop's ``_finalize`` must surface those as
    None while leaving the finite zeros intact.
    """
    index = pd.date_range("2024-01-01", periods=10)
    close = pd.DataFrame({"A": [100.0] * 10}, index=index)
    candidate_ids = ["flat"]
    columns = pd.MultiIndex.from_product(
        [candidate_ids, ["A"]],
        names=["candidate_id", "symbol"],
    )
    # Hold cash the whole time (target weight 0 → zero trades), so win rate and
    # Sharpe are genuinely undefined (NaN) while the other metrics are finite 0.0.
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("flat", "A")] = 0.0
    simulation = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0.0, slippage=0, direction="longonly")
    )
    config = ReportConfig(freq="1D", year_freq="252D")

    candidate_keys = [(c,) for c in candidate_ids]
    result = central_metrics_from_grouped_accessors(
        simulation.portfolio, config, candidate_keys, ["candidate_id"]
    )
    row = result.loc[("flat",)]

    assert row["total_return"] == pytest.approx(0.0)
    assert row["max_dd"] == pytest.approx(0.0)
    assert row["total_trades"] == pytest.approx(0.0)
    assert row["total_fees_paid"] == pytest.approx(0.0)
    assert row["win_rate"] is None, "win_rate should normalise to None when no trades"
    assert row["sharpe_ratio"] is None, "sharpe_ratio should normalise to None for flat returns"

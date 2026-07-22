from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.metrics import make_default_metric_registry
from research.aegis_research.metrics.accessors import (
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from tests.support.research.aegis_research.factories import (
    make_candidate_portfolio,
    make_portfolio_config,
    make_report_config,
)
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
    simulation = make_candidate_portfolio(
        close, allocations, make_portfolio_config(fees=0.001, slippage=0, direction="longonly")
    )
    config = make_report_config(freq="1D", year_freq="252D")

    candidate_keys = [(candidate_id,) for candidate_id in candidate_ids]
    production = central_metrics_from_grouped_accessors(
        simulation,
        config,
        candidate_keys,
        ["candidate_id"],
        make_default_metric_registry().extractors,
    )
    oracle = report_grade_metrics_by_candidate(simulation, config, candidate_ids)

    assert list(production.index) == candidate_keys
    for candidate_id in candidate_ids:
        production_row = production.loc[(candidate_id,)]
        for metric_name in PORTFOLIO_METRIC_VALUE_KEYS:
            _assert_metric_parity(
                production_row[metric_name],
                oracle[candidate_id][metric_name],
                metric_name=f"{candidate_id}/{metric_name}",
            )


def test_non_finite_values_land_as_nan_in_a_float64_grid() -> None:
    """Non-finite metric values land as NaN inside a uniformly float64 grid.

    A flat-price candidate with no closed trades has an undefined win rate and
    Sharpe. The grid carries those as NaN in float64 columns — never as None in
    an object column — so vbt's row_stack concat across windows is dtype-stable
    (an all-None column would trip pandas' deprecated all-NA dtype
    reconciliation, FutureWarning). The None contract lives downstream at the
    optional_float seam (ranking/Evidence), not inside the grid.
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
    simulation = make_candidate_portfolio(
        close, allocations, make_portfolio_config(fees=0.0, slippage=0, direction="longonly")
    )
    config = make_report_config(freq="1D", year_freq="252D")

    candidate_keys = [(c,) for c in candidate_ids]
    result = central_metrics_from_grouped_accessors(
        simulation,
        config,
        candidate_keys,
        ["candidate_id"],
        make_default_metric_registry().extractors,
    )
    row = result.loc[("flat",)]

    assert row["total_return"] == pytest.approx(0.0)
    assert row["max_dd"] == pytest.approx(0.0)
    assert row["total_trades"] == pytest.approx(0.0)
    assert row["total_fees_paid"] == pytest.approx(0.0)
    assert np.isnan(row["win_rate"]), "win_rate should be NaN when no trades"
    assert np.isnan(row["sharpe_ratio"]), "sharpe_ratio should be NaN for flat returns"
    assert result.dtypes.eq("float64").all(), (
        "metric grid must be uniformly float64 — object columns break vbt row_stack dtype stability"
    )

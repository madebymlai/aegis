"""Anti-gaming tests for the carry-pole ranking metrics.

The property under test is the one the metric is hired for: a *smooth-crash*
stream (steady daily premium punctuated by rare large losses - the payoff shape
that games the Sharpe ratio) must rank BELOW an *honest-volatility* stream of
comparable income on the income-utility ranker, even while it ranks ABOVE it on
Sharpe. The tail-budget gate must expose the same hidden left tail.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.custom import optional_custom_metrics
from research.aegis_research.metrics.custom.carry import (
    CARRY_INCOME_UTILITY_DEFINITION,
    CARRY_INCOME_UTILITY_EXTRACTOR,
    CARRY_INCOME_UTILITY_ID,
    CARRY_TAIL_BUDGET_EXTRACTOR,
    CARRY_TAIL_BUDGET_ID,
    carry_utility_rho_sensitivity_from_curve,
)
from research.aegis_research.metrics.custom.support import EquityCurve

_DAYS = 640
_CRASH_DAYS = (200, 450)


def _smooth_crash_returns() -> np.ndarray:
    """Steady +9bp/day with two -20% days: the Sharpe-gaming short-gamma shape."""
    r = np.full(_DAYS, 0.0009)
    r[list(_CRASH_DAYS)] = -0.20
    return r


def _honest_vol_returns() -> np.ndarray:
    """Alternating +/- 1.12% around +2.6bp/day: symmetric, no hidden tail.

    Calibrated so the smooth-crash stream has the HIGHER Sharpe (more income per
    unit of total volatility) while hiding its risk in two crash days.
    """
    sign = np.where(np.arange(_DAYS) % 2 == 0, 1.0, -1.0)
    return 0.00026 + 0.0112 * sign


class _StubPortfolio:
    def __init__(self, value: pd.DataFrame, close: pd.DataFrame) -> None:
        self._value = value
        self.close = close

    def get_value(self) -> pd.DataFrame:
        return self._value


def _stub_portfolio() -> _StubPortfolio:
    index = pd.bdate_range("2021-01-04", periods=_DAYS)
    groups = pd.Index(["smooth_crash", "honest_vol"], name="candidate_id")
    value = pd.DataFrame(
        {
            "smooth_crash": 10_000.0 * np.cumprod(1.0 + _smooth_crash_returns()),
            "honest_vol": 10_000.0 * np.cumprod(1.0 + _honest_vol_returns()),
        },
        index=index,
    )
    value.columns = groups
    close_columns = pd.MultiIndex.from_product(
        [groups, ["TLT"]], names=["candidate_id", SYMBOL_LEVEL]
    )
    close = pd.DataFrame({col: pd.Series(50.0, index=index) for col in close_columns})
    close.columns = close_columns
    return _StubPortfolio(value, close)


def _sharpe(daily: np.ndarray) -> float:
    return float(daily.mean() / daily.std(ddof=1))


def test_income_utility_is_not_gamed_by_the_smooth_crash_stream() -> None:
    """The crossed ordering: higher Sharpe, lower utility - the metric's whole point."""
    pf = _stub_portfolio()
    config = ReportConfig()
    utility = CARRY_INCOME_UTILITY_EXTRACTOR.read(pf, config)

    assert _sharpe(_smooth_crash_returns()) > _sharpe(_honest_vol_returns())
    assert utility["smooth_crash"] < utility["honest_vol"]
    # Both streams still earn: the ranker orders incomes, it does not zero them.
    assert utility["honest_vol"] > 0.0


def test_tail_budget_exposes_the_hidden_left_tail() -> None:
    pf = _stub_portfolio()
    config = ReportConfig()
    budget = CARRY_TAIL_BUDGET_EXTRACTOR.read(pf, config)

    # The crash stream's multi-month left decile is deep; the honest stream's is shallow.
    assert budget["smooth_crash"] < budget["honest_vol"]
    assert budget["smooth_crash"] < 0.0


def test_total_loss_scores_negative_infinity() -> None:
    from research.aegis_research.metrics.custom.carry import _carry_income_utility

    ruined = np.array([0.001] * 100 + [-1.0])
    assert _carry_income_utility(ruined) == float("-inf")


def test_rho_sensitivity_is_deterministic_and_orders_by_risk_aversion() -> None:
    curve = EquityCurve.from_portfolio(_stub_portfolio())
    sensitivity = carry_utility_rho_sensitivity_from_curve(curve)

    # More risk aversion never raises the certainty equivalent of a risky stream.
    row = sensitivity.loc["smooth_crash"]
    assert (row.diff().dropna() <= 0.0).all()
    # The anti-gaming ordering holds across the whole evaluator band, not only at the pin.
    assert (sensitivity.loc["smooth_crash"] < sensitivity.loc["honest_vol"]).all()
    pd.testing.assert_frame_equal(
        sensitivity, carry_utility_rho_sensitivity_from_curve(curve)
    )


def test_carry_metrics_are_registered_opt_in() -> None:
    available = optional_custom_metrics()
    assert CARRY_INCOME_UTILITY_ID in available
    assert CARRY_TAIL_BUDGET_ID in available
    assert available[CARRY_INCOME_UTILITY_ID][0] is CARRY_INCOME_UTILITY_DEFINITION


def test_short_stream_degrades_to_nan() -> None:
    from research.aegis_research.metrics.custom.carry import _carry_income_utility

    assert np.isnan(_carry_income_utility(np.array([0.001, 0.002])))

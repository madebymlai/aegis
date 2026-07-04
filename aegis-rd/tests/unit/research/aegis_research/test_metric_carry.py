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


# ── Robust L-moment skew (the family-membership gate) ──────────────────────────

def test_lskew_is_far_more_outlier_robust_than_moment_skew() -> None:
    """A single injected crash barely moves L-skew but swings moment skew.

    Kim-White's whole point: the third-moment skew is an average of cubed
    deviations, so one outlier dominates it; the L-moment tau_3 moves only
    linearly. The robust gate must not be flipped by a lone print.
    """
    from scipy.stats import skew as moment_skew

    from research.aegis_research.metrics.custom.carry import _l_skewness

    rng = np.random.default_rng(7)
    base = rng.normal(0.0, 0.01, 500)  # symmetric
    contaminated = base.copy()
    contaminated[250] = -0.40  # one crash print

    lskew_shift = abs(_l_skewness(contaminated) - _l_skewness(base))
    moment_shift = abs(moment_skew(contaminated) - moment_skew(base))
    # One 40-sigma print swings the cubed-deviation moment skew by >15 (0 -> ~-15.5);
    # the linear L-moment tau_3 barely moves and stays bounded in (-1, 1).
    assert lskew_shift < 0.20
    assert moment_shift > 20.0 * lskew_shift


def test_lskew_orders_left_skewed_below_symmetric() -> None:
    from research.aegis_research.metrics.custom.carry import _l_skewness

    rng = np.random.default_rng(11)
    symmetric = rng.normal(0.0, 0.01, 2000)
    # Left-skewed: a light-tailed positive body with occasional deep losses.
    left = np.where(rng.random(2000) < 0.05, rng.normal(-0.05, 0.01, 2000),
                    rng.normal(0.003, 0.004, 2000))
    assert _l_skewness(left) < -0.05
    assert abs(_l_skewness(symmetric)) < 0.03
    assert _l_skewness(left) < _l_skewness(symmetric)


def test_carry_downside_lskew_reads_negative_for_smooth_crash() -> None:
    from research.aegis_research.metrics.custom.carry import _carry_downside_lskew

    assert _carry_downside_lskew(_smooth_crash_returns()) < 0.0


def test_downside_lskew_registered_opt_in() -> None:
    from research.aegis_research.metrics.custom.carry import CARRY_DOWNSIDE_LSKEW_ID

    assert CARRY_DOWNSIDE_LSKEW_ID in optional_custom_metrics()


# ── Allocator: role fidelity (the property no single-book metric can see) ──────

def _matched_carry_pair(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A trend stream and two carry candidates with identical standalone stats.

    Both carry candidates are the SAME multiset of daily returns (so identical
    mean, vol, skew, tail, MPPM standalone) - they differ only in WHERE their
    losses land relative to trend: ``independent`` leaves them on their original
    (trend-decoupled) days, while ``cocrashing`` permutes them so the worst carry
    days coincide with trend's worst days. Only a portfolio-aware metric can tell
    them apart. (A perfect anti-sort is deliberately NOT the diversifying ideal: a
    short-gamma pole has no large gains to offset a crash, so anti-sorting only
    relocates its losses onto trend's up-days and, at fixed book vol, buys nothing
    - the realistic, robust contrast is co-crashing vs decoupled.)
    """
    rng = np.random.default_rng(seed)
    n = 1500
    trend = rng.normal(0.0004, 0.011, n)  # convex-ish pole proxy
    # A short-gamma carry stream: steady premium, occasional multi-day losses.
    independent = np.full(n, 0.0004)
    loss_days = rng.choice(n, size=90, replace=False)
    independent[loss_days] = rng.normal(-0.03, 0.01, 90)

    cocrashing = np.empty(n)
    cocrashing[np.argsort(trend)] = np.sort(independent)  # worst carry on worst trend
    return trend, independent, cocrashing


def test_allocator_utility_penalizes_co_crashing_at_matched_standalone_stats() -> None:
    from research.aegis_research.metrics.custom.carry import (
        _carry_income_utility,
        composite_allocator_utility,
        downside_correlation,
    )

    trend, independent, cocrashing = _matched_carry_pair(3)

    # Standalone the two candidates are identical (same multiset of returns), so no
    # single-book metric - MPPM, tail budget, skew - can separate them.
    np.testing.assert_allclose(np.sort(independent), np.sort(cocrashing))
    assert _carry_income_utility(independent) == pytest.approx(_carry_income_utility(cocrashing))

    # In the book, the decoupled pole contributes strictly more certainty-equivalent
    # growth: co-crashing deepens the book's joint tail, which the MPPM prices.
    assert composite_allocator_utility(independent, trend) > composite_allocator_utility(
        cocrashing, trend
    )
    # And the relational guard reads it directly: co-crashing's downside correlation
    # to trend is strongly positive, the decoupled pole's is ~zero.
    assert downside_correlation(cocrashing, trend) > 0.5
    assert downside_correlation(independent, trend) < 0.2


def test_allocator_utility_nan_on_length_mismatch_or_degenerate() -> None:
    from research.aegis_research.metrics.custom.carry import composite_allocator_utility

    trend = np.random.default_rng(1).normal(0.0, 0.01, 500)
    assert np.isnan(composite_allocator_utility(np.zeros(400), trend))  # length mismatch
    assert np.isnan(composite_allocator_utility(np.zeros(500), trend))  # zero-vol carry

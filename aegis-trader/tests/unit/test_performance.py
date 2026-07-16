"""Unit tests for base-currency book performance stats (no engine, no ibapi)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from aegis_trader.portfolio.performance import return_stats


def _equity(values: list[float]) -> pd.Series:
    index = pd.date_range("2020-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=index)


def test_return_stats_include_base_currency_total_return():
    """The headline base-currency total return is the equity curve's end/start - 1,
    independent of the daily path."""
    stats = return_stats(_equity([100.0, 105.0, 102.0, 110.0]))
    assert stats["Total Return (%)"] == pytest.approx(10.0)  # 100 -> 110


def test_return_stats_are_finite_for_a_rising_curve():
    """A steadily rising NAV yields finite return statistics (not the nan a
    multi-currency account's native analyzer would give)."""
    stats = return_stats(_equity([100.0, 101.0, 103.0, 104.0, 107.0]))
    assert math.isfinite(stats["Sharpe Ratio (252 days)"])
    assert math.isfinite(stats["Returns Volatility (252 days)"])


def test_return_stats_sharpe_is_the_annualized_mean_over_std():
    """Sharpe == mean(daily returns)/std × sqrt(252) exactly — pinned on a realistic
    252-day curve (a sane ~0.5, not the extreme a tiny near-constant sample
    annualizes to)."""
    rng = np.random.default_rng(0)
    daily = rng.normal(0.0004, 0.01, 252)
    equity = pd.Series(
        1_000_000.0 * np.cumprod(1.0 + daily),
        index=pd.date_range("2020-01-01", periods=252, freq="D"),
    )
    returns = equity.pct_change().dropna()
    expected = returns.mean() / returns.std() * np.sqrt(252)

    assert expected < 3.0  # a realistic curve gives a believable Sharpe
    assert return_stats(equity)["Sharpe Ratio (252 days)"] == pytest.approx(expected)


def test_return_stats_of_empty_curve_is_empty():
    """No equity samples -> no stats to report (reporting never fails closed)."""
    assert return_stats(pd.Series(dtype=float)) == {}


def test_intraday_sampling_matches_daily_sampling_for_the_same_economic_path():
    """aegis-rd-9qkr.7: equivalent daily paths with one versus many intraday
    NAV observations produce equivalent annualized statistics — Nautilus
    compounds intraday returns into daily returns natively."""
    daily_index = pd.DatetimeIndex(
        ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"], tz="UTC"
    )
    daily_navs = [1_000_000.0, 1_010_000.0, 990_000.0, 1_005_000.0]
    daily = pd.Series(daily_navs, index=daily_index)

    intraday_points = {}
    for day, nav in zip(daily_index, daily_navs, strict=True):
        intraday_points[day + pd.Timedelta(hours=10)] = nav * 1.003
        intraday_points[day + pd.Timedelta(hours=13)] = nav * 0.998
        intraday_points[day + pd.Timedelta(hours=16)] = nav
    intraday = pd.Series(intraday_points).sort_index()

    daily_stats = return_stats(daily)
    intraday_stats = return_stats(intraday)

    for key in ("Sharpe Ratio (252 days)", "Returns Volatility (252 days)", "Sortino Ratio (252 days)"):
        assert intraday_stats[key] == pytest.approx(daily_stats[key])

"""Unit tests for base-currency book performance stats (no engine, no ibapi)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.portfolio.performance import return_stats

_DAILY = derive_horizon(("1D",))
_WEEKLY = derive_horizon(("1W",))


def _equity(values: list[float]) -> pd.Series:
    # Business days: NAV samples come from bars, which never stamp weekends.
    index = pd.date_range("2020-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=index)


def test_return_stats_include_base_currency_total_return():
    """The headline base-currency total return is the equity curve's end/start - 1,
    independent of the daily path."""
    stats = return_stats(_equity([100.0, 105.0, 102.0, 110.0]), horizon=_DAILY)
    assert stats["Total Return (%)"] == pytest.approx(10.0)  # 100 -> 110


def test_return_stats_are_finite_for_a_rising_curve():
    """A steadily rising NAV yields finite return statistics (not the nan a
    multi-currency account's native analyzer would give)."""
    stats = return_stats(_equity([100.0, 101.0, 103.0, 104.0, 107.0]), horizon=_DAILY)
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
        index=pd.date_range("2020-01-01", periods=252, freq="B"),
    )
    returns = equity.pct_change().dropna()
    expected = returns.mean() / returns.std() * np.sqrt(252)

    assert expected < 3.0  # a realistic curve gives a believable Sharpe
    assert return_stats(equity, horizon=_DAILY)["Sharpe Ratio (252 days)"] == pytest.approx(expected)


def test_return_stats_of_empty_curve_is_empty():
    """No equity samples -> no stats to report (reporting never fails closed)."""
    assert return_stats(pd.Series(dtype=float), horizon=_DAILY) == {}


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

    daily_stats = return_stats(daily, horizon=_DAILY)
    intraday_stats = return_stats(intraday, horizon=_DAILY)

    for key in ("Sharpe Ratio (252 days)", "Returns Volatility (252 days)", "Sortino Ratio (252 days)"):
        assert intraday_stats[key] == pytest.approx(daily_stats[key])


def test_weekly_horizon_annualizes_with_52_periods():
    """A weekly-horizon Book's Sharpe is mean(weekly returns)/std x sqrt(52),
    reported under the 52-period key (aegis-rd-cy7l)."""
    friday_closes = pd.DatetimeIndex(
        ["2024-01-05", "2024-01-12", "2024-01-19", "2024-01-26", "2024-02-02"],
        tz="UTC",
    ) + pd.Timedelta(hours=16, minutes=30)
    navs = [1_000_000.0, 1_012_000.0, 1_003_000.0, 1_020_000.0, 1_026_000.0]
    equity = pd.Series(navs, index=friday_closes)
    # The final week is never proven complete, so only the first four Fridays
    # form return rows.
    weekly_returns = pd.Series(navs[:4]).pct_change().dropna()
    expected = weekly_returns.mean() / weekly_returns.std() * np.sqrt(52)

    stats = return_stats(equity, horizon=_WEEKLY)

    assert stats["Sharpe Ratio (52 days)"] == pytest.approx(expected)


def test_weekly_horizon_excludes_the_unproven_final_bucket():
    """A weekly backtest ending mid-week must not annualize the partial week
    as a full row: the trailing Monday point changes Total Return (full
    curve) but none of the annualized statistics."""
    friday_closes = pd.DatetimeIndex(
        ["2024-01-05", "2024-01-12", "2024-01-19", "2024-01-26"], tz="UTC"
    ) + pd.Timedelta(hours=16, minutes=30)
    navs = [1_000_000.0, 1_012_000.0, 1_003_000.0, 1_020_000.0]
    full_weeks = pd.Series(navs, index=friday_closes)
    monday_tail = pd.Timestamp("2024-01-29 21:00", tz="UTC")
    with_partial_week = pd.concat(
        [full_weeks, pd.Series([1_050_000.0], index=[monday_tail])]
    )

    complete_stats = return_stats(full_weeks, horizon=_WEEKLY)
    partial_stats = return_stats(with_partial_week, horizon=_WEEKLY)

    assert partial_stats["Total Return (%)"] == pytest.approx(5.0)
    for key, value in complete_stats.items():
        if key == "Total Return (%)":
            continue
        assert partial_stats[key] == pytest.approx(value), key

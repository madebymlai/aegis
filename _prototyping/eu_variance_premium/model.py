"""Pure statistics for the European variance-risk-premium test.

Question: after Dew-Becker & Giglio (Chicago Fed WP 2025-17) find that the US index-option
variance risk premium's CAPM alpha collapsed to zero at a structural break dated August
2012, does the same collapse show up in European (EURO STOXX 50) data? No free investable
European put-write total-return series could be found (see the prototype README), so the
rigorous risk-adjusted alpha test from the paper cannot be replicated here. What follows is
the fallback the free data *does* support: a raw implied-minus-realized variance gap between
VSTOXX and EURO STOXX 50 realized volatility, split around the same break date. This module
is explicit that the raw gap is not a risk-adjusted return — a positive gap fully explained
by market beta is compensation for holding the index, not "income".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS_PER_YEAR = 252

# VSTOXX is a 30-calendar-day constant-maturity implied-vol index (like VIX). 21 trading
# days is the standard trading-day approximation to a 30-calendar-day window.
VSTOXX_HORIZON_TRADING_DAYS = 21

# A slow, 12-month time-series-momentum lookback: the "slow trend" this sleeve is paired
# against in the book, not a fast/short-horizon trend variant.
SLOW_TREND_LOOKBACK_DAYS = 252

DEFAULT_BREAK_DATE = "2012-08-01"


class InsufficientHistory(ValueError):
    """The supplied series do not overlap enough to support the requested statistic."""


def forward_realized_variance(log_returns: pd.Series, horizon: int) -> pd.Series:
    """Annualized realized variance over the ``horizon`` trading days *after* each date.

    The value at date ``t`` uses log returns for ``(t, t+horizon]`` — the outcome an
    implied-vol quote observed at ``t`` is priced against. This is deliberately
    forward-looking: it measures a historical premium ex post, not a tradeable signal.
    """
    if horizon < 1:
        raise ValueError("horizon must be a positive number of trading days")
    squared = log_returns.pow(2)
    forward_sum = squared.shift(-1).iloc[::-1].rolling(horizon).sum().iloc[::-1]
    return (forward_sum * (TRADING_DAYS_PER_YEAR / horizon)).dropna()


def variance_gap(
    vstoxx_level: pd.Series,
    sx5e_log_returns: pd.Series,
    horizon: int = VSTOXX_HORIZON_TRADING_DAYS,
) -> pd.DataFrame:
    """Align VSTOXX to forward-realized SX5E variance and compute the raw gap.

    Returns one row per trading day with implied/realized variance (annualized,
    fractional units) and the same gap re-expressed in annualized vol points, which is
    the unit the rest of this module reports headline results in.
    """
    common = vstoxx_level.index.intersection(sx5e_log_returns.index)
    if len(common) < horizon + 1:
        raise InsufficientHistory(
            f"only {len(common)} overlapping sessions; need > {horizon}"
        )
    vstoxx = vstoxx_level.loc[common].sort_index()
    returns = sx5e_log_returns.loc[common].sort_index()
    implied_variance = (vstoxx / 100.0) ** 2
    realized_variance = forward_realized_variance(returns, horizon)
    frame = pd.DataFrame(
        {"implied_variance": implied_variance, "realized_variance": realized_variance}
    ).dropna()
    if frame.empty:
        raise InsufficientHistory("no overlapping sessions survive alignment")
    frame["gap_variance"] = frame["implied_variance"] - frame["realized_variance"]
    frame["implied_vol"] = np.sqrt(frame["implied_variance"])
    frame["realized_vol"] = np.sqrt(frame["realized_variance"])
    frame["gap_vol_points"] = (frame["implied_vol"] - frame["realized_vol"]) * 100.0
    return frame


@dataclass(frozen=True)
class NeweyWestMeanTest:
    """A HAC (Newey-West) test of whether a series' mean differs from zero."""

    mean: float
    standard_error: float
    t_statistic: float
    p_value: float
    observations: int
    lags: int


def newey_west_mean_test(x: pd.Series, lags: int) -> NeweyWestMeanTest:
    """HAC standard error of a sample mean, Bartlett-weighted through ``lags``.

    Overlapping-window statistics (ours share up to ``horizon - 1`` days of the same
    forward return window) are serially correlated; a plain iid t-test overstates
    significance. ``lags`` should be at least the overlap length.
    """
    values = x.to_numpy(dtype=float)
    n = values.size
    if n < 2:
        raise InsufficientHistory("need at least two observations for a mean test")
    lags = min(lags, n - 1)
    mean = float(values.mean())
    deviations = values - mean
    gamma0 = float(np.mean(deviations**2))
    long_run_variance = gamma0
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1)
        autocovariance = float(np.mean(deviations[lag:] * deviations[:-lag]))
        long_run_variance += 2.0 * weight * autocovariance
    long_run_variance = max(long_run_variance, 0.0)
    standard_error = float(np.sqrt(long_run_variance / n))
    t_statistic = mean / standard_error if standard_error > 0.0 else float("nan")
    p_value = (
        float(2.0 * stats.norm.sf(abs(t_statistic)))
        if np.isfinite(t_statistic)
        else float("nan")
    )
    return NeweyWestMeanTest(mean, standard_error, t_statistic, p_value, n, lags)


@dataclass(frozen=True)
class StructuralBreakResult:
    """Pre/post subsample means of a series around one break date, each HAC-tested."""

    break_date: str
    pre: NeweyWestMeanTest
    post: NeweyWestMeanTest
    difference: float
    difference_t_statistic: float
    difference_p_value: float


def structural_break_test(
    series: pd.Series, break_date: str, lags: int
) -> StructuralBreakResult:
    """Split ``series`` at ``break_date`` and HAC-test each side and their difference.

    The difference test treats the two subsample means as independent, which ignores
    the handful of forward-window observations straddling the break itself — a minor
    approximation given the subsample sizes this test is meaningful for.
    """
    cut = pd.Timestamp(break_date)
    pre = series.loc[series.index < cut]
    post = series.loc[series.index >= cut]
    if pre.empty or post.empty:
        raise InsufficientHistory(
            f"break date {break_date} leaves one side of the split empty"
        )
    pre_test = newey_west_mean_test(pre, lags)
    post_test = newey_west_mean_test(post, lags)
    difference = post_test.mean - pre_test.mean
    combined_se = float(
        np.sqrt(pre_test.standard_error**2 + post_test.standard_error**2)
    )
    difference_t = difference / combined_se if combined_se > 0.0 else float("nan")
    difference_p = (
        float(2.0 * stats.norm.sf(abs(difference_t)))
        if np.isfinite(difference_t)
        else float("nan")
    )
    return StructuralBreakResult(
        break_date=cut.date().isoformat(),
        pre=pre_test,
        post=post_test,
        difference=difference,
        difference_t_statistic=difference_t,
        difference_p_value=difference_p,
    )


def slow_trend_returns(
    log_returns: pd.Series, lookback: int = SLOW_TREND_LOOKBACK_DAYS
) -> pd.Series:
    """A canonical slow (12-month) time-series-momentum overlay on the same index.

    Position at ``t`` is the sign of the trailing ``lookback``-day return through
    ``t - 1`` — set before ``t`` opens, so it earns (not looks ahead into) day ``t``'s
    return.
    """
    trailing_return = log_returns.rolling(lookback).sum().shift(1)
    position = np.sign(trailing_return)
    return (position * log_returns).dropna()


def daily_short_vol_payoff(
    vstoxx_level: pd.Series, sx5e_log_returns: pd.Series
) -> pd.Series:
    """A one-day short-variance-swap theta-vs-gamma proxy, for loss-state timing only.

    ``implied daily variance priced in at yesterday's close`` minus ``today's realized
    squared return``. This is a simplified single-day proxy distinct from the horizon-
    matched ``variance_gap`` used for the headline structural-break test above.
    """
    common = vstoxx_level.index.intersection(sx5e_log_returns.index)
    vstoxx = vstoxx_level.loc[common].sort_index()
    returns = sx5e_log_returns.loc[common].sort_index()
    implied_daily_variance = (vstoxx.shift(1) / 100.0) ** 2 / TRADING_DAYS_PER_YEAR
    realized_daily_variance = returns.pow(2)
    return (implied_daily_variance - realized_daily_variance).dropna()


@dataclass(frozen=True)
class LossStateOverlap:
    """Whether a slow-trend overlay cushions a short-vol payoff's worst days."""

    correlation: float
    worst_days: int
    trend_return_on_worst_days_mean: float
    trend_return_full_sample_mean: float
    trend_share_positive_on_worst_days: float


def loss_state_overlap(
    short_vol_payoff: pd.Series,
    trend_returns: pd.Series,
    worst_quantile: float = 0.05,
) -> LossStateOverlap:
    """Compare trend's behaviour on short-vol's worst days against its full sample."""
    aligned = pd.concat(
        [short_vol_payoff.rename("short_vol"), trend_returns.rename("trend")], axis=1
    ).dropna()
    if aligned.empty:
        raise InsufficientHistory("short-vol payoff and trend series do not overlap")
    threshold = aligned["short_vol"].quantile(worst_quantile)
    worst = aligned.loc[aligned["short_vol"] <= threshold]
    return LossStateOverlap(
        correlation=float(aligned["short_vol"].corr(aligned["trend"])),
        worst_days=len(worst),
        trend_return_on_worst_days_mean=float(worst["trend"].mean()),
        trend_return_full_sample_mean=float(aligned["trend"].mean()),
        trend_share_positive_on_worst_days=float((worst["trend"] > 0.0).mean()),
    )

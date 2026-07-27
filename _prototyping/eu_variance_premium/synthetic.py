"""Deterministic synthetic VSTOXX/SX5E-like series for demonstrating the model's mechanics.

This is a mechanism check, not a claim about Europe: it exists so a reader can watch the
structural-break test correctly recover a gap it knows was embedded by construction,
without touching the network. The actual verdict about the European variance premium only
comes from ``--live`` mode, which fetches real VSTOXX and EURO STOXX 50 history.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import VSTOXX_HORIZON_TRADING_DAYS, forward_realized_variance

DEFAULT_DAYS = 3000
DEFAULT_BREAK_DATE = "2015-01-05"
DEFAULT_PRE_GAP_VOL_POINTS = 3.0
DEFAULT_POST_GAP_VOL_POINTS = 0.2


@dataclass(frozen=True)
class SyntheticMarket:
    vstoxx_level: pd.Series
    sx5e_log_returns: pd.Series
    break_date: str
    embedded_pre_gap_vol_points: float
    embedded_post_gap_vol_points: float


def synthetic_market(
    days: int = DEFAULT_DAYS,
    break_date: str = DEFAULT_BREAK_DATE,
    pre_gap_vol_points: float = DEFAULT_PRE_GAP_VOL_POINTS,
    post_gap_vol_points: float = DEFAULT_POST_GAP_VOL_POINTS,
    seed: int = 7,
) -> SyntheticMarket:
    """Build a return path, then back out a VSTOXX level with a known embedded gap.

    Returns are generated first; VSTOXX at each date is set to that date's own forward
    realized vol *plus* the target gap, so ``variance_gap`` recovers ``pre_gap_vol_points``
    before ``break_date`` and ``post_gap_vol_points`` after it, up to sampling noise.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2008-01-02", periods=days)
    daily_vol = 0.011 + 0.003 * np.sin(np.arange(days) / 90.0)
    log_returns = pd.Series(rng.normal(0.0002, daily_vol), index=index)

    forward_variance = forward_realized_variance(
        log_returns, VSTOXX_HORIZON_TRADING_DAYS
    )
    forward_vol_points = np.sqrt(forward_variance) * 100.0
    cut = pd.Timestamp(break_date)
    target_gap = pd.Series(
        np.where(
            forward_vol_points.index < cut, pre_gap_vol_points, post_gap_vol_points
        ),
        index=forward_vol_points.index,
    )
    noise = rng.normal(0.0, 0.5, len(forward_vol_points))
    vstoxx_level = (forward_vol_points + target_gap + noise).clip(lower=3.0)
    # The last `horizon` sessions have no forward window to calibrate against; hold the
    # last calibrated level flat rather than leave the tail undefined.
    vstoxx_level = vstoxx_level.reindex(index).ffill().bfill()

    return SyntheticMarket(
        vstoxx_level=vstoxx_level,
        sx5e_log_returns=log_returns,
        break_date=cut.date().isoformat(),
        embedded_pre_gap_vol_points=pre_gap_vol_points,
        embedded_post_gap_vol_points=post_gap_vol_points,
    )

"""Pure cross-period sleeve ledger for Commingled Book analytics.

The ledger owns the rebalance-period observation history and answers the
analytics that need that history: realized sleeve covariance, realized book
skew, per-sleeve P&L attribution, and current drawdown.  It imports no Nautilus
objects and performs no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from aegis_runtime import InstrumentRef

from aegis_trader.domain.allocator import portfolio_skew
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.types import SleeveName

MIN_SLEEVE_VOL_RETURNS = 20
MIN_BOOK_SKEW_RETURNS = 8
TRADING_DAYS_PER_YEAR = 252.0
EWMA_COVARIANCE_ALPHA = 0.06


class SleeveLedger:
    """Accumulate completed rebalance observations and answer book analytics."""

    def __init__(self) -> None:
        self._observations: list[AttributionPeriod] = []

    @property
    def observation_count(self) -> int:
        """Number of completed rebalance observations recorded."""
        return len(self._observations)

    @property
    def nav_history(self) -> tuple[float, ...]:
        """Recorded NAV path, one value per completed rebalance observation."""
        return tuple(period.nav for period in self._observations)

    def record(
        self,
        *,
        nav: float,
        realized_weights: Mapping[InstrumentRef, float],
        sleeve_targets: Mapping[SleeveName, Mapping[InstrumentRef, float]],
        closes: Mapping[InstrumentRef, float],
    ) -> None:
        """Record one completed rebalance period's observation."""
        self._observations.append(
            AttributionPeriod(
                nav=float(nav),
                realized_weights=dict(realized_weights),
                sleeve_targets={name: dict(targets) for name, targets in sleeve_targets.items()},
                closes=dict(closes),
            )
        )

    def realized_covariance(
        self,
        names: Sequence[SleeveName],
        *,
        min_returns: int = MIN_SLEEVE_VOL_RETURNS,
    ) -> dict[SleeveName, dict[SleeveName, float]] | None:
        """Annualized EWMA covariance for complete sleeve return rows.

        Until every requested sleeve has enough complete, non-degenerate returns,
        return ``None`` so the caller can use its base allocation rather than an
        undefined covariance matrix.
        """
        sleeve_names = tuple(names)
        if len(self._observations) < min_returns + 1:
            return None

        periods = self._observations[-(min_returns + 1):]
        rows = _complete_sleeve_return_rows(periods, sleeve_names)
        if len(rows) < min_returns:
            return None
        return _annualized_covariance_by_sleeve(sleeve_names, rows)

    def realized_book_skew(
        self,
        weights: Mapping[SleeveName, float],
        names: Sequence[SleeveName],
        *,
        min_returns: int = MIN_BOOK_SKEW_RETURNS,
    ) -> float | None:
        """Realized skew of the weighted book stream, or ``None`` if too short."""
        sleeve_names = tuple(names)
        rows = _complete_sleeve_return_rows(self._observations, sleeve_names)
        if len(rows) < min_returns:
            return None
        realized_returns = {
            name: tuple(row[index] for row in rows)
            for index, name in enumerate(sleeve_names)
        }
        return portfolio_skew(weights, realized_returns)

    def attribution(self, budgets: Mapping[SleeveName, float]) -> dict[SleeveName, float]:
        """Per-sleeve P&L attribution over the recorded observations."""
        return compute_sleeve_attribution(self._observations, budgets=budgets)

    def current_drawdown(self, current_nav: float) -> float:
        """Current drawdown from the recorded NAV peak plus *current_nav*."""
        if not math.isfinite(current_nav):
            raise ValueError("current NAV must be finite")
        peak = max([float(current_nav), *(float(nav) for nav in self.nav_history)])
        if peak <= 0.0:
            return 0.0
        drawdown = 1.0 - float(current_nav) / peak
        return min(max(drawdown, 0.0), 1.0)


def _complete_sleeve_return_rows(
    periods: Sequence[AttributionPeriod],
    names: tuple[SleeveName, ...],
) -> list[list[float]]:
    """Return period return rows with one valid return per active sleeve."""
    rows: list[list[float]] = []
    for prev, curr in zip(periods, periods[1:], strict=False):
        row = _complete_period_return_row(prev, curr, names)
        if row is not None:
            rows.append(row)
    return rows


def _complete_period_return_row(
    prev: AttributionPeriod,
    curr: AttributionPeriod,
    names: tuple[SleeveName, ...],
) -> list[float] | None:
    row: list[float] = []
    for name in names:
        sleeve_return = _sleeve_period_return(prev, curr, name)
        if sleeve_return is None:
            return None
        row.append(sleeve_return)
    return row


def _sleeve_period_return(
    prev: AttributionPeriod,
    curr: AttributionPeriod,
    name: SleeveName,
) -> float | None:
    sleeve_return = 0.0
    has_input = False
    for figi, weight in prev.sleeve_targets.get(name, {}).items():
        prev_px = prev.closes.get(figi)
        curr_px = curr.closes.get(figi)
        if prev_px is None or curr_px is None or prev_px <= 0:
            continue
        sleeve_return += float(weight) * (curr_px / prev_px - 1.0)
        has_input = True
    return sleeve_return if has_input else None


def _annualized_covariance_by_sleeve(
    names: tuple[SleeveName, ...],
    rows: list[list[float]],
) -> dict[SleeveName, dict[SleeveName, float]] | None:
    covariance = _ewma_covariance(rows, alpha=EWMA_COVARIANCE_ALPHA)
    covariance *= TRADING_DAYS_PER_YEAR
    if not np.all(np.isfinite(covariance)):
        return None
    if np.any(np.diag(covariance) <= 0.0):
        return None
    return _covariance_dict(names, covariance)


def _covariance_dict(
    names: tuple[SleeveName, ...],
    covariance: np.ndarray,
) -> dict[SleeveName, dict[SleeveName, float]]:
    return {
        left: {right: float(covariance[i, j]) for j, right in enumerate(names)}
        for i, left in enumerate(names)
    }


def _ewma_covariance(rows: list[list[float]], *, alpha: float) -> np.ndarray:
    """Return an EWMA covariance matrix for complete return rows."""
    values = np.array(rows, dtype=float)
    mean = values[0].copy()
    covariance = np.zeros((values.shape[1], values.shape[1]), dtype=float)
    for row in values[1:]:
        diff = row - mean
        covariance = (1.0 - alpha) * covariance + alpha * np.outer(diff, diff)
        mean = (1.0 - alpha) * mean + alpha * row
    return (covariance + covariance.T) / 2.0

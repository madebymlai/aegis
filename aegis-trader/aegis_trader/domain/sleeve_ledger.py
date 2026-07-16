"""Pure event-time sleeve ledger for Commingled Book analytics.

The ledger owns the Book's timestamped market-observation history and answers
the analytics that need it: realized sleeve covariance, realized book skew,
per-sleeve P&L attribution, and current drawdown.  It alone owns event
ordering, same-timestamp idempotency, held marks and targets, UTC-day
compounding, complete daily return rows, the internal equity-Book
annualization convention, insufficient-history behavior, and continuous-future
rebasing (aegis-rd-9qkr.7).  It performs no I/O.

Timing contract:

- Drawdown and attribution run at event cadence over every recorded
  observation, so genuine intraday Book risk stays visible.
- Covariance and realized book skew consume only completed UTC-day rows —
  the last observation of each day whose completion a later day's timestamp
  has proven.  A Sleeve callback count is never a statistical horizon.
- A held mark contributes zero movement while a venue is closed; the next
  valid mark realizes the gap return on that later day.  The first observed
  day seeds the basis and yields no return row.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np
from aegis_data.bar_type import timeframe_to_ns
from aegis_data.rebasing import Rebasing
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.allocator import portfolio_skew
from aegis_trader.domain.annualization import EQUITY_BOOK_ANNUALIZATION_PERIODS
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.types import SleeveName

MIN_SLEEVE_VOL_RETURNS = 20
MIN_BOOK_SKEW_RETURNS = 8
EWMA_COVARIANCE_ALPHA = 0.06

_NS_PER_DAY = timeframe_to_ns("1D")


@dataclass(frozen=True)
class BookObservation:
    """One timestamped full-Book market observation.

    ``timestamp_ns`` is the integer UTC event time of the market fact.
    ``marks`` may be partial: only the streams that advanced.  Non-finite or
    missing marks hold the previous valid mark.  ``sleeve_targets`` and
    ``realized_weights`` are full snapshots of the retained Book.
    """

    timestamp_ns: int
    nav: float
    realized_weights: Mapping[InstrumentId, float]
    sleeve_targets: Mapping[SleeveName, Mapping[InstrumentId, float]]
    marks: Mapping[InstrumentId, float]


class DecreasingTimestampError(ValueError):
    """An observation timestamp moved backwards — event order is broken."""

    def __init__(self, timestamp_ns: int, last_timestamp_ns: int) -> None:
        self.timestamp_ns = timestamp_ns
        self.last_timestamp_ns = last_timestamp_ns
        super().__init__(
            f"observation timestamp {timestamp_ns} precedes the last recorded "
            f"timestamp {last_timestamp_ns}; observations must arrive in event order"
        )


class SleeveLedger:
    """Accumulate timestamped Book observations and answer book analytics."""

    def __init__(self) -> None:
        self._timestamps: list[int] = []
        self._observations: list[AttributionPeriod] = []

    @property
    def observation_count(self) -> int:
        """Number of recorded market observations."""
        return len(self._observations)

    @property
    def nav_history(self) -> tuple[float, ...]:
        """Recorded NAV path, one value per recorded observation."""
        return tuple(period.nav for period in self._observations)

    def record(self, observation: BookObservation) -> None:
        """Record one timestamped full-Book market observation.

        Re-recording at the last timestamp folds into that observation without
        creating another return interval — simultaneous partial marks
        accumulate, and recording the same observation twice is a no-op.  A
        decreasing timestamp fails fast.
        """
        last_timestamp = self._timestamps[-1] if self._timestamps else None
        if last_timestamp is not None and observation.timestamp_ns < last_timestamp:
            raise DecreasingTimestampError(observation.timestamp_ns, last_timestamp)

        replacing = last_timestamp is not None and observation.timestamp_ns == last_timestamp
        held_marks = dict(self._observations[-1].closes) if self._observations else {}
        merged_marks = {
            **held_marks,
            **{
                instrument_id: float(mark)
                for instrument_id, mark in observation.marks.items()
                if math.isfinite(mark)
            },
        }
        period = AttributionPeriod(
            nav=float(observation.nav),
            realized_weights=dict(observation.realized_weights),
            sleeve_targets={
                name: dict(targets)
                for name, targets in observation.sleeve_targets.items()
            },
            closes=merged_marks,
        )
        if replacing:
            self._observations[-1] = period
            return
        self._timestamps.append(observation.timestamp_ns)
        self._observations.append(period)

    def rebase_closes(self, rebasings: Mapping[InstrumentId, Rebasing]) -> None:
        """Carry every recorded close for each ref into the new basis via its :class:`Rebasing`.

        A back-adjusted continuous future re-bases its whole price history at each roll — additively
        under a spread mode, multiplicatively under a ratio mode (the :class:`Rebasing` owns which).
        The recorded closes were frozen in the *previous* basis, so cross-period returns spanning the
        roll would divide a new-basis ``curr`` by an old-basis ``prev`` — a cross-basis return that
        desyncs the allocator inputs from research.  Applying the roll's ``Rebasing`` to the stored
        closes keeps the whole recorded history in one basis (the current one), so every return —
        pre-roll, the roll period, and after — is computed in a single consistent basis, matching a
        single-basis research read, for whichever adjustment mode is in force.
        """
        if not rebasings:
            return
        self._observations = [_rebased_period(period, rebasings) for period in self._observations]

    def realized_covariance(
        self,
        names: Sequence[SleeveName],
        *,
        min_returns: int = MIN_SLEEVE_VOL_RETURNS,
    ) -> dict[SleeveName, dict[SleeveName, float]] | None:
        """Annualized EWMA covariance over complete UTC-daily sleeve return rows.

        Until every requested sleeve has enough complete, non-degenerate daily
        returns, return ``None`` so the caller can use its base allocation
        rather than an undefined covariance matrix.
        """
        sleeve_names = tuple(names)
        days = self._completed_daily_snapshots()
        if len(days) < min_returns + 1:
            return None
        rows = _complete_sleeve_return_rows(days[-(min_returns + 1):], sleeve_names)
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
        """Realized skew of the weighted daily book stream, or ``None`` if too short."""
        sleeve_names = tuple(names)
        rows = _complete_sleeve_return_rows(
            self._completed_daily_snapshots(), sleeve_names
        )
        if len(rows) < min_returns:
            return None
        return portfolio_skew(weights, _return_series_by_sleeve(sleeve_names, rows))

    def attribution(self, budgets: Mapping[SleeveName, float]) -> dict[SleeveName, float]:
        """Per-sleeve P&L attribution over the recorded event intervals."""
        return compute_sleeve_attribution(self._observations, budgets=budgets)

    def current_drawdown(self, current_nav: float) -> float:
        """Current drawdown from the recorded NAV peak plus *current_nav*."""
        if not math.isfinite(current_nav):
            raise ValueError("current NAV must be finite")
        peak = max([float(current_nav), *(float(period.nav) for period in self._observations)])
        if peak <= 0.0:
            return 0.0
        drawdown = 1.0 - float(current_nav) / peak
        return min(max(drawdown, 0.0), 1.0)

    def _completed_daily_snapshots(self) -> list[AttributionPeriod]:
        """The last observation of each completed UTC day, in day order.

        The latest observed day is never returned: only a later day's
        timestamp proves a day complete, so the current (possibly still open)
        day stays out of risk inputs.
        """
        by_day: dict[int, AttributionPeriod] = {}
        for timestamp, period in zip(self._timestamps, self._observations, strict=True):
            by_day[timestamp // _NS_PER_DAY] = period
        if not by_day:
            return []
        days = sorted(by_day)
        return [by_day[day] for day in days[:-1]]


def _rebased_period(
    period: AttributionPeriod,
    rebasings: Mapping[InstrumentId, Rebasing],
) -> AttributionPeriod:
    """Return *period* with each ref's close carried into the new basis by its Rebasing (others
    untouched)."""
    closes = dict(period.closes)
    for ref, rebasing in rebasings.items():
        if ref in closes:
            closes[ref] = rebasing.apply(closes[ref])
    return replace(period, closes=closes)


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
    for ref, weight in prev.sleeve_targets.get(name, {}).items():
        prev_price = prev.closes.get(ref)
        curr_price = curr.closes.get(ref)
        if prev_price is None or curr_price is None or prev_price <= 0:
            continue
        sleeve_return += float(weight) * (curr_price / prev_price - 1.0)
        has_input = True
    return sleeve_return if has_input else None


def _return_series_by_sleeve(
    names: tuple[SleeveName, ...],
    rows: Sequence[Sequence[float]],
) -> dict[SleeveName, tuple[float, ...]]:
    return {
        name: tuple(row[index] for row in rows)
        for index, name in enumerate(names)
    }


def _annualized_covariance_by_sleeve(
    names: tuple[SleeveName, ...],
    rows: Sequence[Sequence[float]],
) -> dict[SleeveName, dict[SleeveName, float]] | None:
    covariance = _ewma_covariance(rows, alpha=EWMA_COVARIANCE_ALPHA)
    covariance = _shrink_covariance(covariance, _ledoit_wolf_intensity(rows))
    covariance *= EQUITY_BOOK_ANNUALIZATION_PERIODS
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


def _ewma_covariance(rows: Sequence[Sequence[float]], *, alpha: float) -> np.ndarray:
    """Return an EWMA covariance matrix for complete return rows."""
    values = np.array(rows, dtype=float)
    mean = values[0].copy()
    covariance = np.zeros((values.shape[1], values.shape[1]), dtype=float)
    for row in values[1:]:
        diff = row - mean
        covariance = (1.0 - alpha) * covariance + alpha * np.outer(diff, diff)
        mean = (1.0 - alpha) * mean + alpha * row
    return (covariance + covariance.T) / 2.0


def _constant_correlation_target(covariance: np.ndarray) -> np.ndarray:
    """The Ledoit-Wolf (2004) shrinkage target: every correlation replaced by the mean.

    Variances (the diagonal) are preserved, so realized sleeve vols are untouched —
    shrinkage only regularizes the correlation structure. For two sleeves the mean
    of the single pair is that pair, so the target equals the estimate and
    shrinkage is a no-op; it binds from three sleeves up.
    """
    vols = np.sqrt(np.diag(covariance))
    correlation = covariance / np.outer(vols, vols)
    n = correlation.shape[0]
    if n < 2:
        return covariance.copy()
    mean_rho = (correlation.sum() - np.trace(correlation)) / (n * (n - 1))
    target = mean_rho * np.outer(vols, vols)
    np.fill_diagonal(target, np.diag(covariance))
    return target


def _shrink_covariance(covariance: np.ndarray, intensity: float) -> np.ndarray:
    """Linear shrinkage toward the constant-correlation target.

    With ~17 effective observations (EWMA alpha 0.06) over a handful of sleeves,
    estimated correlations are mostly noise; pulling them toward their
    cross-sectional mean cuts the ERC allocator's risk-contribution error without
    ever hurting it (validated 2026-07-03: 16 structure/size regimes x 500 trials,
    worst-cell regression 0.0%, near-orthogonal roster -27..-41% RC deviation).
    """
    if intensity <= 0.0:
        return covariance
    return (1.0 - intensity) * covariance + intensity * _constant_correlation_target(covariance)


def _ledoit_wolf_intensity(rows: Sequence[Sequence[float]]) -> float:
    """Analytic Ledoit-Wolf (2004) intensity for the constant-correlation target.

    Computed with the sample-covariance formula over the same return rows the EWMA
    estimate consumes and applied to that EWMA matrix — the exact combination the
    promotion evidence validated (the formula's asymptotics assume a sample
    covariance; treat a re-derivation under EWMA weights as future refinement, not
    a correctness fix). Self-tunes across regimes (~0.9 when correlations are
    noise, ~0.1 when genuine structure has enough data) so there is no config knob.
    Returns 0.0 (no shrinkage) when there are too few rows or sleeves to estimate.
    """
    values = np.array(rows, dtype=float)
    t, n = values.shape
    if t < 3 or n < 2:
        return 0.0
    demeaned = values - values.mean(axis=0)
    sample = demeaned.T @ demeaned / t
    diag = np.diag(sample)
    if np.any(diag <= 0.0) or not np.all(np.isfinite(sample)):
        return 0.0
    vols = np.sqrt(diag)
    correlation = sample / np.outer(vols, vols)
    mean_rho = (correlation.sum() - n) / (n * (n - 1))

    # pi-hat: total asymptotic variance of the sample covariance entries.
    squared = demeaned**2
    pi_matrix = (squared.T @ squared) / t - sample**2
    pi_hat = pi_matrix.sum()

    # rho-hat: diagonal entries exact, off-diagonal via the theta terms.
    theta = ((demeaned**3).T @ demeaned) / t - vols[:, None] ** 2 * sample
    off_diagonal = ~np.eye(n, dtype=bool)
    rho_hat = np.trace(pi_matrix) + mean_rho * (
        ((1.0 / vols)[:, None] * vols[None, :]) * theta
    )[off_diagonal].sum()

    # gamma-hat: squared Frobenius distance between target and sample.
    target = mean_rho * np.outer(vols, vols)
    np.fill_diagonal(target, diag)
    gamma_hat = ((target - sample) ** 2).sum()
    if gamma_hat <= 0.0 or not math.isfinite(gamma_hat):
        return 0.0
    return float(np.clip((pi_hat - rho_hat) / gamma_hat / t, 0.0, 1.0))

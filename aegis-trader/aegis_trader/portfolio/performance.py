"""Base-currency performance reporting for a multi-currency book backtest.

Nautilus' ``PortfolioAnalyzer`` cannot produce a single return series for a
multi-currency (``base_currency=None``) account — it falls back to position
returns and yields ``nan`` headline stats (a documented Nautilus limitation).
Following the documented remedy ("compute portfolio returns externally by
converting balances to a common currency"), this module records the book NAV in
the book's base currency on each bar (via :class:`NautilusBookState`, the same
base-converted valuation the sizer marks against) and runs the standard return
statistics over that single-currency equity curve.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nautilus_trader.analysis import (
    PortfolioAnalyzer,
    ProfitFactor,
    ReturnsAverage,
    ReturnsAverageLoss,
    ReturnsAverageWin,
    ReturnsVolatility,
    RiskReturnRatio,
    SharpeRatio,
    SortinoRatio,
)
from nautilus_trader.common.actor import Actor
from nautilus_trader.config import ActorConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Currency

from aegis_trader.domain.analytics_horizon import AnalyticsHorizon
from aegis_trader.portfolio.book_state import NautilusBookState

_NS_PER_DAY = 86_400_000_000_000


class BookEquityRecorderConfig(ActorConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """What the recorder needs: the book base currency and the bars to sample on."""

    base_currency: str
    bar_types: tuple[str, ...]


class BookEquityRecorder(Actor):
    """Samples book NAV (in the book's base currency) on each bar into an equity curve.

    A reporting-only actor: it never trades.  On each subscribed bar it reads the
    base-converted NAV and stores it keyed by the bar timestamp (last write wins
    per timestamp, so many instruments on one date yield one NAV point).
    """

    def __init__(self, config: BookEquityRecorderConfig) -> None:
        super().__init__(config)
        self._base_currency = config.base_currency
        self._bar_types = config.bar_types
        self._samples: dict[pd.Timestamp, float] = {}
        self._book_state: NautilusBookState | None = None

    def on_start(self) -> None:
        covered = frozenset(
            BarType.from_str(raw).instrument_id
            for raw in self._bar_types
        )
        self._book_state = NautilusBookState(
            portfolio=self.portfolio,
            cache=self.cache,
            base_currency=Currency.from_str(self._base_currency),
            covered_instrument_ids=covered,
        )
        for raw in self._bar_types:
            self.subscribe_bars(BarType.from_str(raw))

    def on_bar(self, bar: Bar) -> None:
        if self._book_state is not None:
            self._samples[pd.Timestamp(bar.ts_event, tz="UTC")] = self._book_state.nav()

    @property
    def equity_curve(self) -> pd.Series:
        """Book NAV in base currency, one point per sampled bar timestamp."""
        if not self._samples:
            return pd.Series(dtype=float)
        return pd.Series(self._samples).sort_index()


# The return-based statistics Nautilus' Portfolio registers by default (PnL- and
# order-based ones don't apply to a bare returns series); kept in sync so the
# reported keys match the engine's native ``stats_returns``.  The annualized
# ones are constructed with the Book's derived analytics horizon
# (aegis-rd-cy7l), never a cadence inferred from callbacks.
def _return_statistics(periods_per_year: int) -> list[Any]:
    # list[Any]: the nautilus stubs don't expose PortfolioStatistic as the
    # statistics' base class, so a precise annotation cannot type-check.
    statistics: list[Any] = [
        ReturnsVolatility(period=periods_per_year),
        ReturnsAverage(),
        ReturnsAverageLoss(),
        ReturnsAverageWin(),
        SharpeRatio(period=periods_per_year),
        SortinoRatio(period=periods_per_year),
        ProfitFactor(),
        RiskReturnRatio(),
    ]
    return statistics


def return_stats(equity: pd.Series, *, horizon: AnalyticsHorizon) -> dict[str, float]:
    """Standard return statistics (Sharpe, volatility, …) over a single-currency
    NAV equity curve — the multi-currency remedy Nautilus' own analyzer omits.

    A fresh ``PortfolioAnalyzer`` has no statistics registered (the engine's
    Portfolio registers them), so the default return-based set is registered here
    before feeding the returns derived from the equity curve.  The curve is
    sampled at each horizon bucket's last NAV through the same ``bucket_of``
    rule the Sleeve Ledger uses, so a faster stream's intraday callbacks can
    never multiply the sample count (aegis-rd-9qkr.7, aegis-rd-cy7l) —
    statistics themselves stay Nautilus-native.  Daily buckets keep the final
    bucket (a finished curve's last day is complete); coarser buckets drop it
    (nothing proves a mid-week end complete, and a partial week must not
    annualize as a full row).  The base-currency headline ``Total Return (%)``
    (end/start - 1) is added over the full event-time curve.  An equity curve
    with no return yields no stats.
    """
    if len(equity) < 2:
        return {}
    sampled = _bucket_last(equity, horizon)
    if horizon.bucket_width_ns > _NS_PER_DAY:
        sampled = sampled.iloc[:-1]
    returns = sampled.pct_change().dropna()
    if returns.empty:
        return {}
    analyzer = PortfolioAnalyzer()
    for statistic in _return_statistics(horizon.periods_per_year):
        analyzer.register_statistic(statistic)
    for timestamp, value in returns.items():
        analyzer.add_return(timestamp.to_pydatetime(), float(value))
    stats = dict(analyzer.get_performance_stats_returns())
    stats["Total Return (%)"] = (equity.iloc[-1] / equity.iloc[0] - 1.0) * 100.0
    return stats


def _bucket_last(equity: pd.Series, horizon: AnalyticsHorizon) -> pd.Series:
    """The last NAV of each horizon bucket, indexed by its event timestamp."""
    per_bucket: dict[int, tuple[pd.Timestamp, float]] = {}
    for timestamp, nav in equity.items():
        per_bucket[horizon.bucket_of(int(timestamp.value))] = (timestamp, float(nav))
    ordered = [per_bucket[bucket] for bucket in sorted(per_bucket)]
    return pd.Series(
        [nav for _, nav in ordered],
        index=pd.DatetimeIndex([timestamp for timestamp, _ in ordered]),
    )

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

from aegis_trader.portfolio.book_state import NautilusBookState


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
        self._book_state = NautilusBookState(
            portfolio=self.portfolio,
            cache=self.cache,
            base_currency=Currency.from_str(self._base_currency),
            instrument_ref_for_id=lambda _instrument_id: None,
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
# reported keys match the engine's native ``stats_returns``.
_RETURN_STATISTICS: tuple[type, ...] = (
    ReturnsVolatility,
    ReturnsAverage,
    ReturnsAverageLoss,
    ReturnsAverageWin,
    SharpeRatio,
    SortinoRatio,
    ProfitFactor,
    RiskReturnRatio,
)


def return_stats(equity: pd.Series) -> dict[str, float]:
    """Standard return statistics (Sharpe, volatility, …) over a single-currency
    NAV equity curve — the multi-currency remedy Nautilus' own analyzer omits.

    A fresh ``PortfolioAnalyzer`` has no statistics registered (the engine's
    Portfolio registers them), so the default return-based set is registered here
    before feeding the per-bar returns derived from the equity curve.  The
    base-currency headline ``Total Return (%)`` (end/start - 1) is added too.
    An equity curve with no return (fewer than two points) yields no stats.
    """
    returns = equity.pct_change().dropna()
    if returns.empty:
        return {}
    analyzer = PortfolioAnalyzer()
    for statistic in _RETURN_STATISTICS:
        analyzer.register_statistic(statistic())
    for timestamp, value in returns.items():
        analyzer.add_return(timestamp.to_pydatetime(), float(value))
    stats = dict(analyzer.get_performance_stats_returns())
    stats["Total Return (%)"] = (equity.iloc[-1] / equity.iloc[0] - 1.0) * 100.0
    return stats

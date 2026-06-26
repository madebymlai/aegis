"""Market data behind a narrow Cache-backed port (ADR-0003, Wave B).

A *deep* port: it hides the Strategy's ``cache.instrument(...)`` and
``cache.bars(...)`` reads behind instrument sizing, quantity construction, FX,
and completed-period bar-window/freshness methods.  The sole adapter,
:class:`NautilusMarketData`, implements it over Nautilus's own ``CacheFacade``.

One concern, one Nautilus implementation — so the Protocol and its adapter live
in one module.  The port/adapter file split is reserved for the multi-impl
bundle registry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd
from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency, Quantity
from aegis_trader.data.bar_type import raw_bar_type
from aegis_trader.domain.sizing import InstrumentSizing


@dataclass(frozen=True)
class MarketBar:
    """One completed native market bar in pure value form."""

    ts_event: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@runtime_checkable
class MarketDataPort(Protocol):
    """Cache-backed market-data reads the rebalance overlay depends on."""

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing | None:
        """Sizing metadata (quote currency + size increment), or ``None`` when
        the instrument is not in the reconciled cache."""
        ...

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> Quantity | None:
        """A venue-valid order quantity from a raw share count, or ``None`` when
        the instrument is not in the reconciled cache."""
        ...

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        """The real instrument an order for ``instrument_id`` trades — a continuous root maps to
        its current dated front leg; a native instrument is itself."""
        ...

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        """FX rate as quote units per 1 base (base→quote, e.g. EUR→GBP = 0.85),
        or ``None`` when no rate is available — the overlay fails closed rather
        than fabricating a rate."""
        ...

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        """Latest ``limit`` bars for ``ref`` ending at the completed period.

        The read is Cache-backed and excludes bars at or after the completed
        period's right edge, preserving the one-bar-lag/no-look-ahead contract
        even when the trigger bar is already present in the Cache.
        """
        ...

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        """Whether the Cache contains a bar for ``ref`` in the completed period."""
        ...


@runtime_checkable
class ContinuousSeriesPort(Protocol):
    """The read port's view of a continuous-future feed: the synthetic root it owns, its series
    (the signal data), and the current front leg (the real instrument sizing/execution resolve to).
    """

    @property
    def continuous_id(self) -> InstrumentId:
        """The synthetic continuous-root id this feed materializes (e.g. ``ES.XCME``)."""
        ...

    def series(self) -> pd.DataFrame:
        """The current back-adjusted continuous OHLCV frame (UTC-naive index)."""
        ...

    def front_contract(self) -> InstrumentId:
        """The current dated front leg — the real cached instrument an order trades."""
        ...


class NautilusMarketData:
    """MarketDataPort backed by the Nautilus Cache, with continuous roots read from feeds.

    Raw instruments are read from the cache by their raw bar type; continuous-future roots are
    read from their feed's back-adjusted series (Model 2 — the continuous series never lives in
    the live cache), so the rebalance lookback sees the adjusted series for either kind alike.
    """

    def __init__(
        self, *, cache: CacheFacade, feeds: Sequence[ContinuousSeriesPort] = ()
    ) -> None:
        self._cache = cache
        self._feeds = {feed.continuous_id: feed for feed in feeds}

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing | None:
        instrument = self._cache.instrument(self.execution_instrument_id(instrument_id))
        if instrument is None:
            return None
        return InstrumentSizing(
            currency=instrument.quote_currency.code,
            size_increment=float(instrument.size_increment),
            multiplier=float(instrument.multiplier),
        )

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> Quantity | None:
        instrument = self._cache.instrument(self.execution_instrument_id(instrument_id))
        if instrument is None:
            return None
        return instrument.make_qty(raw_shares)

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        """The real instrument an order trades for *instrument_id*: a continuous root resolves to
        its feed's current front leg (the synthetic root is never a cached, tradeable instrument);
        anything else is itself."""
        feed = self._feeds.get(instrument_id)
        return feed.front_contract() if feed is not None else instrument_id

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        if base_currency == quote_currency:
            return 1.0
        rate = self._cache.get_mark_xrate(
            Currency.from_str(base_currency), Currency.from_str(quote_currency)
        )
        if rate is None or rate <= 0.0:
            return None
        return float(rate)

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        period_end = _period_end(period, period_ns)
        completed = [
            bar
            for bar in self._market_bars(instrument_id, timeframe)
            if bar.ts_event < period_end
        ]
        return tuple(completed[-limit:])

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        period_start, period_end = _period_bounds(period, period_ns)
        return any(
            period_start <= bar.ts_event < period_end
            for bar in self._market_bars(instrument_id, timeframe)
        )

    def _market_bars(self, instrument_id: InstrumentId, timeframe: str) -> list[MarketBar]:
        """Chronological market bars for an instrument: a continuous root from its feed's
        re-based series, a raw instrument from the cache by its raw bar type."""
        feed = self._feeds.get(instrument_id)
        if feed is not None:
            return _frame_to_market_bars(feed.series())
        # Cache.bars returns newest-first; bundles need chronological arrays.
        cache_bars = self._cache.bars(raw_bar_type(instrument_id, timeframe))
        return [_to_market_bar(bar) for bar in reversed(cache_bars)]


def _period_bounds(period: int, period_ns: int) -> tuple[int, int]:
    period_start = period * period_ns
    return period_start, _period_end(period, period_ns)


def _period_end(period: int, period_ns: int) -> int:
    return (period + 1) * period_ns


def _frame_to_market_bars(frame: pd.DataFrame) -> list[MarketBar]:
    """Project a continuous feed's OHLCV frame (UTC-naive index) into chronological MarketBars."""
    return [
        MarketBar(
            ts_event=pd.Timestamp(index, tz="UTC").value,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=float(row["Volume"]),
        )
        for index, row in frame.iterrows()
    ]


def _to_market_bar(bar: Bar) -> MarketBar:
    return MarketBar(
        ts_event=bar.ts_event,
        open=float(bar.open.as_double()),
        high=float(bar.high.as_double()),
        low=float(bar.low.as_double()),
        close=float(bar.close.as_double()),
        volume=float(bar.volume.as_double()),
    )

"""Market data behind a narrow Cache-backed port (ADR-0003, Wave B).

A *deep* port: it hides the Strategy's ``cache.instrument(...)`` and
``cache.bars(...)`` reads behind instrument sizing, quantity construction, FX,
and completed-period bar-window/freshness methods.  The sole adapter,
:class:`NautilusMarketData`, implements it over Nautilus's own ``CacheFacade``.

One concern, one Nautilus implementation — so the Protocol and its adapter live
in one module.  The port/adapter file split is reserved for multi-impl concerns
(``bundles/``, ``observability/``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency, Quantity
from aegis_runtime import InstrumentRef

from aegis_trader.data.bar_type import bar_type
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

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        """FX rate as quote units per 1 base (base→quote, e.g. EUR→GBP = 0.85),
        or ``None`` when no rate is available — the overlay fails closed rather
        than fabricating a rate."""
        ...

    def lookback_window(
        self,
        ref: InstrumentRef,
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
        ref: InstrumentRef,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        """Whether the Cache contains a bar for ``ref`` in the completed period."""
        ...


class NautilusMarketData:
    """MarketDataPort backed by the Nautilus Cache read interface."""

    def __init__(self, *, cache: CacheFacade) -> None:
        self._cache = cache

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing | None:
        instrument = self._cache.instrument(instrument_id)
        if instrument is None:
            return None
        return InstrumentSizing(
            currency=instrument.quote_currency.code,
            size_increment=float(instrument.size_increment),
        )

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> Quantity | None:
        instrument = self._cache.instrument(instrument_id)
        if instrument is None:
            return None
        return instrument.make_qty(raw_shares)

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
        _ref: InstrumentRef,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        period_end = _period_end(period, period_ns)
        bars = _completed_bars(
            self._cache_bars(instrument_id, timeframe),
            period_end=period_end,
        )
        return tuple(_to_market_bar(bar) for bar in bars[-limit:])

    def has_bar_in_period(
        self,
        _ref: InstrumentRef,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        period_start, period_end = _period_bounds(period, period_ns)
        return any(
            period_start <= bar.ts_event < period_end
            for bar in self._cache_bars(instrument_id, timeframe)
        )

    def _cache_bars(self, instrument_id: InstrumentId, timeframe: str) -> list[Bar]:
        return self._cache.bars(bar_type(instrument_id.value, timeframe))


def _period_bounds(period: int, period_ns: int) -> tuple[int, int]:
    period_start = period * period_ns
    return period_start, _period_end(period, period_ns)


def _period_end(period: int, period_ns: int) -> int:
    return (period + 1) * period_ns


def _completed_bars(bars: list[Bar], *, period_end: int) -> list[Bar]:
    # Cache.bars returns newest-first; bundles need chronological arrays.
    return [bar for bar in reversed(bars) if bar.ts_event < period_end]


def _to_market_bar(bar: Bar) -> MarketBar:
    return MarketBar(
        ts_event=bar.ts_event,
        open=float(bar.open.as_double()),
        high=float(bar.high.as_double()),
        low=float(bar.low.as_double()),
        close=float(bar.close.as_double()),
        volume=float(bar.volume.as_double()),
    )

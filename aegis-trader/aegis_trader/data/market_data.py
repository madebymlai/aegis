"""Instrument reference data behind a narrow port (ADR-0003, Wave B).

A *deep* port: it hides the Strategy's ``cache.instrument(...)`` reads behind two
methods — per-instrument sizing metadata and Nautilus quantity construction.
The sole adapter, :class:`NautilusMarketData`, implements it over Nautilus's own
``CacheFacade``, delegating sizing metadata and quantity construction to the
Nautilus ``Instrument`` itself.

One concern, one Nautilus implementation — so the Protocol and its adapter live
in one module.  The port/adapter file split is reserved for multi-impl concerns
(``bundles/``, ``observability/``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency, Quantity

from aegis_trader.domain.sizing import InstrumentSizing


@runtime_checkable
class MarketDataPort(Protocol):
    """Instrument reference-data reads the rebalance overlay depends on."""

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

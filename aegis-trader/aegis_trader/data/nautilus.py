"""NautilusMarketData — MarketDataPort over Nautilus's CacheFacade.

Deep adapter: collapses the kernel's ``cache.instrument(...)`` reads into the
narrow :class:`~aegis_trader.data.port.MarketDataPort`.  Sizing metadata and
quantity construction are delegated to the Nautilus ``Instrument`` itself.
"""

from __future__ import annotations

from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity

from aegis_trader.domain.sizing import InstrumentSizing


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

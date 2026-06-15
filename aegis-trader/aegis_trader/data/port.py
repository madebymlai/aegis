"""MarketDataPort — the Trader's narrow view of instrument reference data.

A *deep* port (ADR-0003): it hides the Strategy's ``cache.instrument(...)`` reads
behind two methods — per-instrument sizing metadata and Nautilus quantity
construction.  The Nautilus-backed adapter (``data/nautilus.py``) implements it
over Nautilus's ``CacheFacade``, so the Strategy never reaches into the kernel
cache for instrument detail.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity

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

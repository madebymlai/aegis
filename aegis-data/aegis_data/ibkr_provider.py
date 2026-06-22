"""The concrete IBKR ``NautilusDataProviderPort`` for research (ADR-0006/0008).

A research cache miss fills from IBKR identically to live.  This adapter wraps
Nautilus's standalone ``HistoricInteractiveBrokersClient`` — the client "for
backtesting and research" — and:

- is **pure fetch**: ``request_bars`` *returns* bars; :class:`CatalogBackedDataPort`
  is the single writer of record (ADR-0008).  Same for ``request_instruments``.
- **hides ``asyncio``** behind the synchronous port: the historic client is async,
  so every call connects, requests, and disconnects inside one ``asyncio.run``.
- resolves identity through IB **simplified symbology** — the native
  ``InstrumentId`` value (``SYMBOL.VENUE``) is the IBKR request id; no bespoke
  resolver (ADR-0005).

IBKR (``ibapi``) is a true-external dependency, so the historic client is
imported lazily — importing this module never requires ``ibapi``.  Connection
parameters mirror the IB Gateway defaults; the operator points them at the
running gateway.  Instrument *definitions* are a separate Step-1 write
(:func:`seed_instrument_definitions`), not per-window fill data (ADR-0008).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.instruments import Instrument

# IB Gateway defaults (paper port); the operator overrides for a live gateway.
IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_CLIENT_ID = 1
IB_MARKET_DATA_TYPE = "REALTIME"
IB_REQUEST_TIMEOUT = 120

# IB ``MarketDataTypeEnum`` member names — validated up front so a bad value fails
# at construction, not at connect time, without importing ``ibapi`` to do it.
_IB_MARKET_DATA_TYPES = frozenset({"REALTIME", "FROZEN", "DELAYED", "DELAYED_FROZEN"})


@dataclass(frozen=True)
class IbkrHistoricalProvider:
    """Pure-fetch IBKR data provider over the standalone historic client.

    ``client_factory`` exists for testing: a fake async client stands in for the
    real ``HistoricInteractiveBrokersClient`` so the param-translation and
    asyncio-hiding can be verified without IBKR.  Left ``None`` in production, the
    real client is lazily constructed.
    """

    host: str = IB_HOST
    port: int = IB_PORT
    client_id: int = IB_CLIENT_ID
    market_data_type: str = IB_MARKET_DATA_TYPE
    use_rth: bool = True
    timeout: int = IB_REQUEST_TIMEOUT
    client_factory: Callable[[], Any] | None = None

    def __post_init__(self) -> None:
        if self.market_data_type not in _IB_MARKET_DATA_TYPES:
            raise ValueError(
                f"unknown IB market_data_type {self.market_data_type!r}; "
                f"expected one of {sorted(_IB_MARKET_DATA_TYPES)}"
            )

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> Sequence[Bar]:
        """The vendor-aggregated bars for *bar_type* over ``[start, end]``."""
        return asyncio.run(
            self._with_client(
                lambda client: client.request_bars(
                    bar_specifications=[str(bar_type.spec)],
                    start_date_time=start.to_pydatetime(),
                    end_date_time=end.to_pydatetime(),
                    tz_name="UTC",
                    instrument_ids=[bar_type.instrument_id.value],
                    use_rth=self.use_rth,
                    timeout=self.timeout,
                )
            )
        )

    def request_instruments(
        self, instrument_ids: Sequence[InstrumentId]
    ) -> Sequence[Instrument]:
        """The IBKR instrument definitions for *instrument_ids* (Step-1 write)."""
        return asyncio.run(
            self._with_client(
                lambda client: client.request_instruments(
                    instrument_ids=[
                        instrument_id.value for instrument_id in instrument_ids
                    ],
                )
            )
        )

    async def _with_client(
        self, call: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        client = self._make_client()
        await client.connect()
        try:
            return await call(client)
        finally:
            await client.disconnect()

    def _make_client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory()
        from ibapi.common import MarketDataTypeEnum
        from nautilus_trader.adapters.interactive_brokers.historical.client import (
            HistoricInteractiveBrokersClient,
        )

        return HistoricInteractiveBrokersClient(
            host=self.host,
            port=self.port,
            client_id=self.client_id,
            market_data_type=getattr(MarketDataTypeEnum, self.market_data_type),
        )


def seed_instrument_definitions(
    catalog: Any,
    provider: IbkrHistoricalProvider,
    instrument_ids: Sequence[InstrumentId],
) -> None:
    """Persist instrument definitions to *catalog* (the Step-1 write, ADR-0008).

    Definitions are a **separate lifecycle** from the per-window bar fill — static
    setup, not windowed data (ADR-0008, ISP: the bar port is not widened). It is
    **idempotent**: only the definitions missing from *catalog* are fetched and
    written, so calling it is free when they are already present — which is what
    lets the lazy fill trigger it on a backfill without making a warm read connect
    to IBKR. The provider *fetches* definitions, aegis-data *writes* them.
    """
    missing = _missing_definitions(catalog, instrument_ids)
    if not missing:
        return
    instruments = provider.request_instruments(missing)
    if instruments:
        catalog.write_data(list(instruments))


def _missing_definitions(
    catalog: Any, instrument_ids: Sequence[InstrumentId]
) -> list[InstrumentId]:
    present = {
        instrument.id
        for instrument in catalog.instruments(
            instrument_ids=[instrument_id.value for instrument_id in instrument_ids]
        )
    }
    return [instrument_id for instrument_id in instrument_ids if instrument_id not in present]


__all__ = [
    "IbkrHistoricalProvider",
    "seed_instrument_definitions",
]

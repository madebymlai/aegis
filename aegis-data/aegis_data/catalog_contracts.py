"""Catalog-backed dated-leg source for the continuous-future chain.

The chain (:mod:`aegis_data.chain`) is provider-neutral: it takes injected callables
to list a root's dated contracts, fetch a leg's OHLCV, and probe a leg's daily volume.
This module implements those three seams over the Nautilus catalog — instrument
**definitions** name the dated legs and their last-trade dates; stored **bars** supply
prices and volume — so research and live build the same chain from the one corpus
(replacing the deleted Databento port).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract

from aegis_data.catalog import CatalogBackedDataPort, RawBarRequest
from aegis_data.chain import ContractCalendar, ContractFetcher, VolumeProbe
from aegis_data.roll import DatedContract


def catalog_contract_calendar(catalog: Any) -> ContractCalendar:
    """List a root's outright dated legs from the catalog's ``FuturesContract`` definitions.

    Each leg is named by its native ``InstrumentId`` value and dated by its expiration;
    the run is expiry-ordered.  The window is the caller's (the roll schedule selects
    the front-between legs), so every listed contract for the root is returned.
    """

    def list_contracts(root: str, start, end) -> Sequence[DatedContract]:  # noqa: ANN001, ARG001
        legs = [
            DatedContract(
                symbol=instrument.id.value,
                last_trade=instrument.expiration_utc.date(),
            )
            for instrument in catalog.instruments(instrument_type=FuturesContract)
            if instrument.underlying == root
        ]
        return sorted(legs, key=lambda leg: leg.last_trade)

    return list_contracts


def catalog_contract_fetcher(
    port: CatalogBackedDataPort, *, timeframe: str = "1D"
) -> ContractFetcher:
    """Fetch one leg's OHLCV over ``[start, end]`` through the catalog port.

    The port owns the catalog read (and any allowed lazy fill + coverage gate), so a
    missing leg fails loud rather than silently truncating the chain.
    """

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        instrument_id = InstrumentId.from_str(symbol)
        request = RawBarRequest(
            (instrument_id,), start.isoformat(), end.isoformat(), timeframe
        )
        return port.load_raw_bars(request)[instrument_id]

    return fetch


def catalog_volume_probe(
    port: CatalogBackedDataPort, *, timeframe: str = "1D"
) -> VolumeProbe:
    """Probe one leg's daily volume over ``[start, end]`` for liquidity-leadership ranking.

    Reuses the leg fetcher and reads its ``Volume`` array — daily regardless of the
    deliverable bar cadence (ADR-0001), since inclusion is a low-frequency decision.
    """
    fetch = catalog_contract_fetcher(port, timeframe=timeframe)

    def probe(symbol: str, start: date, end: date) -> pd.Series:
        return fetch(symbol, start, end)["Volume"]

    return probe


__all__ = [
    "catalog_contract_calendar",
    "catalog_contract_fetcher",
    "catalog_volume_probe",
]

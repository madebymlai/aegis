"""Catalog-backed dated-leg source (aegis-data).

The chain's injected seams — list a root's dated contracts, fetch a leg's OHLCV,
probe a leg's daily volume — read from the Nautilus catalog (instrument definitions
+ stored bars), replacing the deleted Databento port.  Tested against fakes so the
seams stay provider-free.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.catalog_contracts import (
    catalog_contract_calendar,
    catalog_contract_fetcher,
    catalog_volume_probe,
)
from aegis_data.roll import DatedContract


def _futures(instrument_id: str, underlying: str, expiry: str) -> FuturesContract:
    iid = InstrumentId.from_str(instrument_id)
    return FuturesContract(
        instrument_id=iid,
        raw_symbol=iid.symbol,
        asset_class=AssetClass.INDEX,
        exchange=iid.venue.value,
        currency=USD,
        price_precision=2,
        price_increment=Price(0.01, 2),
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        underlying=underlying,
        activation_ns=0,
        expiration_ns=pd.Timestamp(expiry, tz="UTC").value,
        ts_event=0,
        ts_init=0,
    )


class _FakeCatalog:
    def __init__(self, instruments: list[FuturesContract]) -> None:
        self._instruments = instruments

    def instruments(self, instrument_type: type | None = None, **_kwargs: object) -> list:
        return [
            instrument
            for instrument in self._instruments
            if instrument_type is None or isinstance(instrument, instrument_type)
        ]


def _ohlcv(dates: list[str], close: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": close, "High": [c + 1 for c in close], "Low": [c - 1 for c in close],
         "Close": close, "Volume": [1000.0] * len(close)},
        index=pd.to_datetime(dates),
    )


class _FakeReader:
    """A catalog port stand-in: records requests, returns canned per-leg OHLCV."""

    def __init__(self, frames: dict[InstrumentId, pd.DataFrame]) -> None:
        self._frames = frames
        self.requests: list = []

    def load_raw_bars(self, request) -> dict:  # noqa: ANN001
        self.requests.append(request)
        return {iid: self._frames[iid] for iid in request.instrument_ids}


def test_calendar_lists_a_roots_dated_legs_from_catalog_definitions() -> None:
    catalog = _FakeCatalog(
        [
            _futures("ESM4.XCME", "ES", "2024-06-21"),
            _futures("ESH4.XCME", "ES", "2024-03-15"),
            _futures("CLF4.NYMEX", "CL", "2024-01-22"),
        ]
    )
    calendar = catalog_contract_calendar(catalog)

    legs = calendar("ES", date(2024, 1, 1), date(2024, 12, 31))

    assert legs == [
        DatedContract("ESH4.XCME", date(2024, 3, 15)),
        DatedContract("ESM4.XCME", date(2024, 6, 21)),
    ]


def test_fetcher_reads_a_legs_ohlcv_over_its_window_via_the_catalog_port() -> None:
    instrument_id = InstrumentId.from_str("ESH4.XCME")
    frame = _ohlcv(["2024-01-02", "2024-01-03"], [100.0, 101.0])
    reader = _FakeReader({instrument_id: frame})
    fetch = catalog_contract_fetcher(reader)

    result = fetch("ESH4.XCME", date(2024, 1, 1), date(2024, 3, 1))

    assert result.equals(frame)
    assert reader.requests[0].instrument_ids == (instrument_id,)
    assert reader.requests[0].start == "2024-01-01"
    assert reader.requests[0].end == "2024-03-01"


def test_volume_probe_reads_a_legs_daily_volume() -> None:
    instrument_id = InstrumentId.from_str("ESH4.XCME")
    frame = _ohlcv(["2024-01-02", "2024-01-03"], [100.0, 101.0])
    reader = _FakeReader({instrument_id: frame})
    probe = catalog_volume_probe(reader)

    volume = probe("ESH4.XCME", date(2024, 1, 1), date(2024, 3, 1))

    assert volume.equals(frame["Volume"])

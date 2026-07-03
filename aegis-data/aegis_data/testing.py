"""Shared test fakes for the catalog port and continuous-futures fixtures.

Importable test support (the ``pandas.testing`` pattern) so aegis-data and the
packages that consume it drive the same fake corpus instead of copying it:

- ``FakeCatalog`` — a ``ParquetDataCatalog`` stand-in: instrument definitions
  plus native bars by identifier.  Usable beneath the real
  ``CatalogBackedDataPort`` or beneath ``FakePort``.
- ``FakePort`` — a ``CatalogBackedDataPort`` stand-in: OHLCV frames for the
  chain, the fake catalog beneath.
- ``es_port`` / ``es_port_two_rolls`` / ``early_crossover_es_port`` — canned ES
  scenarios: one liquidity migration, two rolls, and an early crossover.

Bars carry a single 21:00 UTC close stamp for both ``ts_event`` and
``ts_init``; consumers key off the event date and the bucket-close ceiling,
which this convention satisfies.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pandas as pd
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import (
    ContinuousRootLegsNotFoundError,
    ContinuousRootVenueMismatchError,
    RawBarRequest,
    ResolvedContinuousRoot,
)
from aegis_data.roll import DatedContract

ES_START = "2024-01-15"
ES_END = "2024-05-31"

_UTC = timezone.utc
_CLOSE = time(21, 0)
_PRECISION = 2
_CROSSOVER = pd.Timestamp("2024-03-01")


def future(
    instrument_id: str, expiry: str, *, underlying: str = "ES"
) -> FuturesContract:
    """A dated futures-contract definition for the fake catalog."""
    iid = InstrumentId.from_str(instrument_id)
    return FuturesContract(
        instrument_id=iid,
        raw_symbol=iid.symbol,
        asset_class=AssetClass.INDEX,
        exchange=iid.venue.value,
        currency=USD,
        price_precision=_PRECISION,
        price_increment=Price(10**-_PRECISION, _PRECISION),
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        underlying=underlying,
        activation_ns=0,
        expiration_ns=pd.Timestamp(expiry, tz="UTC").value,
        ts_event=0,
        ts_init=0,
    )


def frame(start: str, end: str, base: float, *, leads_early: bool) -> pd.DataFrame:
    """A business-day OHLCV frame whose volume leads before or after the crossover."""
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    volume = [(1000.0 if (day < _CROSSOVER) == leads_early else 100.0) for day in idx]
    return _ohlcv(idx, close, volume)


def lead_frame(
    start: str, end: str, base: float, lead_lo: str, lead_hi: str
) -> pd.DataFrame:
    """A business-day OHLCV frame whose volume leads inside ``[lead_lo, lead_hi]``."""
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    lo, hi = pd.Timestamp(lead_lo), pd.Timestamp(lead_hi)
    volume = [1000.0 if lo <= day <= hi else 50.0 for day in idx]
    return _ohlcv(idx, close, volume)


def _ohlcv(
    idx: pd.DatetimeIndex, close: list[float], volume: list[float]
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def bars(instrument_id: InstrumentId, ohlcv: pd.DataFrame) -> list[Bar]:
    """Native daily bars for an OHLCV frame, stamped at the 21:00 UTC close."""
    bar_type = raw_bar_type(instrument_id, "1D")
    out: list[Bar] = []
    for day, row in ohlcv.iterrows():
        ts = int(datetime.combine(day.date(), _CLOSE, _UTC).timestamp() * 1e9)
        out.append(
            Bar(
                bar_type,
                Price.from_str(str(row["Open"])),
                Price.from_str(str(row["High"])),
                Price.from_str(str(row["Low"])),
                Price.from_str(str(row["Close"])),
                Quantity.from_int(int(row["Volume"])),
                ts,
                ts,
            )
        )
    return out


class FakeCatalog:
    """A ParquetDataCatalog stand-in: instrument definitions + native bars by identifier."""

    def __init__(
        self, instruments: list[FuturesContract], bars: dict[str, list[Bar]]
    ) -> None:
        self._instruments = instruments
        self._bars = bars

    def instruments(
        self,
        instrument_type: type | None = None,
        instrument_ids: list[str] | None = None,
        **_kwargs: object,
    ) -> list[FuturesContract]:
        out = self._instruments
        if instrument_type is not None:
            out = [i for i in out if isinstance(i, instrument_type)]
        if instrument_ids is not None:
            wanted = set(instrument_ids)
            out = [i for i in out if i.id.value in wanted]
        return out

    def query(
        self,
        data_cls: type,  # noqa: ARG002 - Bar only in this fixture
        identifiers: list[str] | None = None,
        start: object = None,
        end: object = None,
        **_kwargs: object,
    ) -> list[Bar]:
        lo, hi = pd.Timestamp(start).value, pd.Timestamp(end).value
        return [
            bar
            for ident in (identifiers or [])
            for bar in self._bars.get(ident, [])
            if lo <= bar.ts_event <= hi
        ]

    def get_missing_intervals_for_request(
        self, *_args: object, **_kwargs: object
    ) -> list:
        return []


class FakePort:
    """A CatalogBackedDataPort stand-in: OHLCV frames for the chain, the catalog beneath."""

    def __init__(
        self, catalog: FakeCatalog, frames: dict[InstrumentId, pd.DataFrame]
    ) -> None:
        self.catalog = catalog
        self._frames = frames

    def load_raw_bars(self, request: RawBarRequest) -> dict[InstrumentId, pd.DataFrame]:
        start, end = pd.Timestamp(request.start), pd.Timestamp(request.end)
        return {
            iid: self._frames[iid].loc[
                (self._frames[iid].index >= start) & (self._frames[iid].index <= end)
            ]
            for iid in request.instrument_ids
        }

    def read_native_bars(self, request: RawBarRequest) -> dict[InstrumentId, list[Bar]]:
        return {
            iid: self.catalog.query(
                Bar,
                identifiers=[str(raw_bar_type(iid, request.timeframe))],
                start=request.start,
                end=request.end,
            )
            for iid in request.instrument_ids
        }

    def instruments(
        self, instrument_ids: tuple[InstrumentId, ...]
    ) -> list[FuturesContract]:
        return self.catalog.instruments(
            instrument_ids=[instrument_id.value for instrument_id in instrument_ids]
        )

    def fetch_contract_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        instrument_id = InstrumentId.from_str(symbol)
        return self.load_raw_bars(
            RawBarRequest(
                (instrument_id,), start.isoformat(), end.isoformat(), timeframe
            )
        )[instrument_id]

    def probe_contract_volume(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        timeframe: str = "1D",
    ) -> pd.Series:
        return self.fetch_contract_ohlcv(symbol, start, end, timeframe=timeframe)[
            "Volume"
        ]

    def _continuous_root_legs(self, root: str) -> list[DatedContract]:
        legs = [
            DatedContract(
                symbol=instrument.id.value,
                last_trade=instrument.expiration_utc.date(),
            )
            for instrument in self.catalog.instruments(instrument_type=FuturesContract)
            if instrument.underlying == root
        ]
        return sorted(legs, key=lambda leg: leg.last_trade)

    def resolve_continuous(self, root: str) -> ResolvedContinuousRoot:
        legs = tuple(self._continuous_root_legs(root))
        if not legs:
            raise ContinuousRootLegsNotFoundError(
                f"no dated legs in the catalog for continuous-future root {root!r}"
            )
        venues = {InstrumentId.from_str(leg.symbol).venue for leg in legs}
        if len(venues) != 1:
            raise ContinuousRootVenueMismatchError(
                f"continuous-future root {root!r} legs span multiple venues "
                f"{sorted(venue.value for venue in venues)}; expected one"
            )
        return ResolvedContinuousRoot(InstrumentId(Symbol(root), next(iter(venues))), legs)


def es_port() -> tuple[FakePort, dict[InstrumentId, list[Bar]]]:
    """ES with two legs and one liquidity migration at the crossover."""
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    frames = {
        esh4: frame(ES_START, "2024-03-15", 100.0, leads_early=True),
        esm4: frame(ES_START, "2024-04-30", 200.0, leads_early=False),
    }
    return _port(
        frames,
        [future("ESH4.XCME", "2024-03-15"), future("ESM4.XCME", "2024-06-21")],
    )


def es_port_two_rolls() -> tuple[FakePort, dict[InstrumentId, list[Bar]]]:
    """ES with three legs and two liquidity-led rolls."""
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    esu4 = InstrumentId.from_str("ESU4.XCME")
    frames = {
        esh4: lead_frame(ES_START, "2024-03-15", 100.0, ES_START, "2024-02-29"),
        esm4: lead_frame(ES_START, "2024-06-21", 200.0, "2024-03-01", "2024-06-06"),
        esu4: lead_frame("2024-03-01", "2024-09-19", 300.0, "2024-06-07", "2024-09-19"),
    }
    return _port(
        frames,
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XCME", "2024-06-21"),
            future("ESU4.XCME", "2024-09-20"),
        ],
    )


def early_crossover_es_port() -> FakePort:
    """ES with three legs where liquidity crosses to the back leg early."""
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    esu4 = InstrumentId.from_str("ESU4.XCME")
    frames = {
        esh4: lead_frame(ES_START, "2024-03-15", 100.0, ES_START, "2024-02-29"),
        esm4: lead_frame(ES_START, "2024-06-21", 200.0, "2024-03-01", "2024-04-14"),
        esu4: lead_frame("2024-03-01", "2024-09-19", 300.0, "2024-04-15", "2024-09-19"),
    }
    port, _native = _port(
        frames,
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XCME", "2024-06-21"),
            future("ESU4.XCME", "2024-09-20"),
        ],
    )
    return port


def _port(
    frames: dict[InstrumentId, pd.DataFrame], instruments: list[FuturesContract]
) -> tuple[FakePort, dict[InstrumentId, list[Bar]]]:
    native = {iid: bars(iid, ohlcv) for iid, ohlcv in frames.items()}
    catalog = FakeCatalog(
        instruments=instruments,
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
    )
    return FakePort(catalog, frames), native


__all__ = [
    "ES_END",
    "ES_START",
    "FakeCatalog",
    "FakePort",
    "bars",
    "early_crossover_es_port",
    "es_port",
    "es_port_two_rolls",
    "frame",
    "future",
    "lead_frame",
]

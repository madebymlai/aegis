from __future__ import annotations

from datetime import datetime, time, timezone

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

_UTC = timezone.utc
_CLOSE = time(21, 0)
_PRECISION = 2
_CROSSOVER = pd.Timestamp("2024-03-01")
_START, _END = "2024-01-15", "2024-05-31"


def _future(
    instrument_id: str, expiry: str, *, underlying: str = "ES"
) -> FuturesContract:
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


def _frame(start: str, end: str, base: float, *, leads_early: bool) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    volume = [(1000.0 if (day < _CROSSOVER) == leads_early else 100.0) for day in idx]
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


def _bars(instrument_id: InstrumentId, frame: pd.DataFrame) -> list[Bar]:
    bar_type = raw_bar_type(instrument_id, "1D")
    bars: list[Bar] = []
    for day, row in frame.iterrows():
        ts = int(datetime.combine(day.date(), _CLOSE, _UTC).timestamp() * 1e9)
        bars.append(
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
    return bars


class _FakeCatalog:
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


class _FakePort:
    """A CatalogBackedDataPort stand-in: OHLCV frames for the chain, the catalog beneath."""

    def __init__(
        self, catalog: _FakeCatalog, frames: dict[InstrumentId, pd.DataFrame]
    ) -> None:
        self.catalog = catalog
        self._frames = frames
        self.read_native_bars_count = 0

    def load_raw_bars(self, request: object) -> dict[InstrumentId, pd.DataFrame]:
        start, end = pd.Timestamp(request.start), pd.Timestamp(request.end)  # type: ignore[attr-defined]
        return {
            iid: self._frames[iid].loc[
                (self._frames[iid].index >= start) & (self._frames[iid].index <= end)
            ]
            for iid in request.instrument_ids  # type: ignore[attr-defined]
        }

    def read_native_bars(self, request: object) -> dict[InstrumentId, list[Bar]]:
        self.read_native_bars_count += 1
        return {
            iid: self.catalog.query(  # type: ignore[attr-defined]
                Bar,
                identifiers=[str(raw_bar_type(iid, request.timeframe))],  # type: ignore[attr-defined]
                start=request.start,  # type: ignore[attr-defined]
                end=request.end,  # type: ignore[attr-defined]
            )
            for iid in request.instrument_ids  # type: ignore[attr-defined]
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
        start,
        end,
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
        start,
        end,
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


def _es_port() -> tuple[_FakePort, dict[InstrumentId, list[Bar]]]:
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    frames = {
        esh4: _frame(_START, "2024-03-15", 100.0, leads_early=True),
        esm4: _frame(_START, "2024-04-30", 200.0, leads_early=False),
    }
    native = {iid: _bars(iid, frame) for iid, frame in frames.items()}
    catalog = _FakeCatalog(
        instruments=[
            _future("ESH4.XCME", "2024-03-15"),
            _future("ESM4.XCME", "2024-06-21"),
        ],
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
    )
    return _FakePort(catalog, frames), native

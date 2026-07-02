"""Catalog-driven continuous-future materialisation (aegis-data, model path).

``ContinuousContractModel`` is the entry point RD and Trader call: given the
catalog-backed port and a bare root, it builds the dated-leg chain through the
catalog seams, hands the roll-transition table to Nautilus's engine, and exposes the
adjusted continuous OHLCV keyed by the synthetic root id — never persisting a continuous
series.

The arithmetic is byte-exact-tested elsewhere (``test_continuous_golden``); here the
output is cross-checked against the independent Decimal spread oracle to prove the
*catalog wiring* feeds the proven materialiser correctly (right legs, window, key).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog_contracts import (
    catalog_contract_calendar,
    catalog_contract_fetcher,
    catalog_volume_probe,
)
from aegis_data.chain import fetch_contract_chain
from aegis_data.continuous_catalog import (
    continuous_instrument_ids,
)
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.continuous_future import continuous_future
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from tests.support.continuous_oracle import backward_series

_UTC = timezone.utc
_CLOSE = time(21, 0)  # bar stamp, strictly after the midnight roll boundary
_PRECISION = 2
_RAW_SCALE = 10**16
_CROSSOVER = pd.Timestamp("2024-03-01")  # liquidity migrates ESH4 -> ESM4 here
_START, _END = "2024-01-15", "2024-05-31"


def _future(instrument_id: str, expiry: str, *, underlying: str = "ES") -> FuturesContract:
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
    # ESH4 leads (high volume) before the crossover; ESM4 leads after — so both are ever
    # the Liquidity Leader and the chain rolls between them on the migration.
    volume = [
        (1000.0 if (day < _CROSSOVER) == leads_early else 100.0) for day in idx
    ]
    return pd.DataFrame(
        {"Open": [c - 0.5 for c in close], "High": [c + 1 for c in close],
         "Low": [c - 1 for c in close], "Close": close, "Volume": volume},
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
        data_cls: type,  # noqa: ARG002 — Bar only in this fixture
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


def _es_port() -> tuple[_FakePort, dict[InstrumentId, list[Bar]]]:
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    frames = {
        esh4: _frame(_START, "2024-03-15", 100.0, leads_early=True),
        esm4: _frame(_START, "2024-04-30", 200.0, leads_early=False),
    }
    native = {iid: _bars(iid, frame) for iid, frame in frames.items()}
    catalog = _FakeCatalog(
        instruments=[_future("ESH4.XCME", "2024-03-15"), _future("ESM4.XCME", "2024-06-21")],
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
    )
    return _FakePort(catalog, frames), native


def test_continuous_contract_model_matches_the_oracle_keyed_by_root_id() -> None:
    port, native = _es_port()

    # Build the chain through the same catalog seams the composer uses, then cross-check
    # the engine's adjusted series against the independent Decimal oracle for the default mode.
    chain = fetch_contract_chain(
        "ES", date(2024, 1, 15), date(2024, 5, 31),
        list_contracts=catalog_contract_calendar(port.catalog),
        fetch=catalog_contract_fetcher(port),
        bar_cadence=timedelta(days=1),
        probe_volume=catalog_volume_probe(port),
    )
    future = continuous_future(chain, InstrumentId.from_str("ES.XCME"))
    oracle = backward_series(native, future.transitions, mode=DEFAULT_ADJUSTMENT_MODE)

    model = ContinuousContractModel(port, "ES", start=_START, timeframe="1D")
    model.materialize(end=_END)

    assert model.continuous_id == InstrumentId.from_str("ES.XCME")
    frame = model.frame
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.index.is_monotonic_increasing and not frame.index.has_duplicates

    head = oracle[: len(frame)]
    assert frame["Close"].tolist() == pytest.approx([o.close_raw / _RAW_SCALE for o in head])
    assert frame["Open"].tolist() == pytest.approx([o.open_raw / _RAW_SCALE for o in head])
    # The first emitted bar is a pre-leg bar carried up by the seam (not raw 99.5).
    assert frame["Open"].iloc[0] != pytest.approx(99.5)


def test_continuous_instrument_ids_resolve_without_materialising_bars() -> None:
    port, _ = _es_port()

    resolved = continuous_instrument_ids(port, ["ES"], start=_START, end=_END)

    assert resolved == (InstrumentId.from_str("ES.XCME"),)
    assert port.read_native_bars_count == 0


def test_continuous_contract_model_rejects_legs_across_venues() -> None:
    # A continuous future is one venue's cycle; mismatched-venue legs fail loud.
    catalog = _FakeCatalog(
        instruments=[_future("ESH4.XCME", "2024-03-15"), _future("ESM4.XEUR", "2024-06-21")],
        bars={},
    )
    port = _FakePort(catalog, {})

    model = ContinuousContractModel(port, "ES", start=_START)

    with pytest.raises(ValueError, match="span multiple venues"):
        model.materialize(end=_END)

def test_continuous_instrument_ids_reject_legs_across_venues() -> None:
    catalog = _FakeCatalog(
        instruments=[_future("ESH4.XCME", "2024-03-15"), _future("ESM4.XEUR", "2024-06-21")],
        bars={},
    )
    port = _FakePort(catalog, {})

    with pytest.raises(ValueError, match="span multiple venues"):
        continuous_instrument_ids(port, ["ES"], start=_START, end=_END)


def test_continuous_contract_model_rejects_a_root_with_no_legs() -> None:
    catalog = _FakeCatalog(
        instruments=[_future("CLF4.NYMEX", "2024-01-22", underlying="CL")], bars={}
    )
    port = _FakePort(catalog, {})
    model = ContinuousContractModel(port, "ES", start=_START)

    with pytest.raises(ValueError, match="no dated legs"):
        model.materialize(end=_END)

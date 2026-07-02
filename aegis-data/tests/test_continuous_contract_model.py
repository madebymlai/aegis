"""ContinuousContractModel interface tests."""

from __future__ import annotations

from datetime import date

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import bars_to_ohlcv
from aegis_data.continuous_contract_model import ContinuousContractModel
from tests.test_continuous_catalog import (
    _START,
    _FakeCatalog,
    _FakePort,
    _bars,
    _es_port,
    _future,
)

_ES_XCME = InstrumentId.from_str("ES.XCME")
_ESH4 = InstrumentId.from_str("ESH4.XCME")
_ESM4 = InstrumentId.from_str("ESM4.XCME")
_ESU4 = InstrumentId.from_str("ESU4.XCME")


def _lead_frame(start: str, end: str, base: float, lead_lo: str, lead_hi: str) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    lo, hi = pd.Timestamp(lead_lo), pd.Timestamp(lead_hi)
    volume = [1000.0 if lo <= day <= hi else 50.0 for day in idx]
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


def _es_port_two_rolls() -> tuple[_FakePort, dict[InstrumentId, list[Bar]]]:
    frames = {
        _ESH4: _lead_frame(_START, "2024-03-15", 100.0, _START, "2024-02-29"),
        _ESM4: _lead_frame(_START, "2024-06-21", 200.0, "2024-03-01", "2024-06-06"),
        _ESU4: _lead_frame("2024-03-01", "2024-09-19", 300.0, "2024-06-07", "2024-09-19"),
    }
    native = {iid: _bars(iid, frame) for iid, frame in frames.items()}
    catalog = _FakeCatalog(
        instruments=[
            _future("ESH4.XCME", "2024-03-15"),
            _future("ESM4.XCME", "2024-06-21"),
            _future("ESU4.XCME", "2024-09-20"),
        ],
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
    )
    return _FakePort(catalog, frames), native


def _bar_on(native: dict[InstrumentId, list[Bar]], instrument_id: InstrumentId, day: date) -> Bar:
    return next(
        bar
        for bar in native[instrument_id]
        if pd.Timestamp(bar.ts_event, tz="UTC").date() == day
    )


def _ohlcv_row(bar: Bar) -> pd.DataFrame:
    row = bars_to_ohlcv([bar])
    close_stamp = pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None)
    row.index = pd.DatetimeIndex([close_stamp])
    return row


def test_materialize_exposes_frame_id_and_schedule_front() -> None:
    port, _native = _es_port()
    model = ContinuousContractModel(port, "ES", start=_START, timeframe="1D")

    model.materialize(end="2024-02-15")

    assert model.continuous_id == _ES_XCME
    assert model.front_leg == _ESH4
    assert model.front_leg_as_of("2024-05-31") == _ESM4
    assert list(model.frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert model.frame.index.is_monotonic_increasing


def test_on_bar_appends_a_front_leg_bar_at_offset_zero() -> None:
    port, native = _es_port()
    model = ContinuousContractModel(port, "ES", start=_START, timeframe="1D")
    model.materialize(end="2024-04-29")
    before = model.frame.copy()
    bar = _bar_on(native, _ESM4, date(2024, 4, 30))

    model.on_bar(bar)

    assert model.front_leg == _ESM4
    assert len(model.frame) == len(before) + 1
    pd.testing.assert_frame_equal(model.frame.tail(1), _ohlcv_row(bar))


def test_roll_rematerializes_rebased_and_records_rebasing() -> None:
    port, native = _es_port_two_rolls()
    model = ContinuousContractModel(port, "ES", start=_START, timeframe="1D")
    model.materialize(end="2024-06-10")
    pre = model.frame.copy()
    roll_bar = _bar_on(native, _ESU4, date(2024, 6, 14))

    model.on_bar(roll_bar)

    assert model.front_leg == _ESU4
    common = pre.index.intersection(model.frame.index)
    carried = pre.loc[common, "Close"].map(model.last_rebasing.apply)
    assert carried.iloc[-1] != pre.loc[common[-1], "Close"]
    pd.testing.assert_series_equal(
        model.frame.loc[common, "Close"], carried, check_names=False, rtol=1e-3
    )

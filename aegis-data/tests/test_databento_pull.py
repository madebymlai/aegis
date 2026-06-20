"""Databento futures Pull through the Nautilus-backed raw-leg store."""

from __future__ import annotations

from datetime import date

import pandas as pd
from aegis_runtime import FuturesRef

from aegis_data.calendars import TradingCalendar
from aegis_data.databento_pull import pull_databento_futures_bars
from aegis_data.roll import DatedContract
from aegis_data.store import (
    NATIVE_OHLCV_ARRAYS,
    NativeBarsRequest,
    native_bars_path,
    raw_futures_leg_path,
    read_native_bars,
)

_BASIS = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}


def _leg_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    close = [_BASIS[symbol] + offset for offset in range(len(index))]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1.0 for value in close],
            "Low": [value - 1.0 for value in close],
            "Close": close,
            "Volume": [1000.0] * len(index),
        },
        index=index,
    )


def _request(ref: FuturesRef) -> NativeBarsRequest:
    return NativeBarsRequest(
        refs=(ref,),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-01-02",
        end="2025-01-01",
        calendar=TradingCalendar.XNYS,
    )


def _provider_hit(symbol: str, start: date, end: date) -> pd.DataFrame:
    raise AssertionError(f"provider hit for {symbol} in [{start}, {end}]")


def _es_calendar(root: str, start: date, end: date) -> list[DatedContract]:
    return [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
        DatedContract("ESZ4", date(2024, 12, 20)),
    ]


def test_databento_pull_materializes_continuous_history_from_retained_raw_legs(tmp_path) -> None:
    ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    fetched: list[str] = []

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        fetched.append(symbol)
        return _leg_bars(symbol, start, end)

    pull_databento_futures_bars(
        _request(ref), fetcher=fetch, contract_calendar=_es_calendar, store_dir=tmp_path
    )
    first = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2025-01-01",
        store_dir=tmp_path,
        calendar=TradingCalendar.XNYS,
    )

    native_bars_path(ref, "1D", store_dir=tmp_path).unlink()
    pull_databento_futures_bars(
        _request(ref),
        fetcher=_provider_hit,
        contract_calendar=_es_calendar,
        store_dir=tmp_path,
    )
    second = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2025-01-01",
        store_dir=tmp_path,
        calendar=TradingCalendar.XNYS,
    )

    assert fetched == ["ESH4", "ESM4", "ESU4", "ESZ4"]
    assert raw_futures_leg_path("GLBX.MDP3", "ESH4", "1D", store_dir=tmp_path).exists()
    assert not first[ref]["Close"].isna().any()
    pd.testing.assert_frame_equal(first[ref], second[ref])


def test_databento_pull_derives_alternate_adjustment_from_same_raw_legs(tmp_path) -> None:
    backward_ratio_ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    backward_spread_ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_spread")

    pull_databento_futures_bars(
        _request(backward_ratio_ref),
        fetcher=_leg_bars,
        contract_calendar=_es_calendar,
        store_dir=tmp_path,
    )
    pull_databento_futures_bars(
        _request(backward_spread_ref),
        fetcher=_provider_hit,
        contract_calendar=_es_calendar,
        store_dir=tmp_path,
    )
    frames = read_native_bars(
        (backward_ratio_ref, backward_spread_ref),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2025-01-01",
        store_dir=tmp_path,
        calendar=TradingCalendar.XNYS,
    )

    assert native_bars_path(backward_ratio_ref, "1D", store_dir=tmp_path) != native_bars_path(
        backward_spread_ref, "1D", store_dir=tmp_path
    )
    assert (
        frames[backward_ratio_ref]["Close"].iloc[0] != frames[backward_spread_ref]["Close"].iloc[0]
    )

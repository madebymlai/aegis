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
_ES_LAST_TRADE = {
    "ESH4": date(2024, 3, 15),
    "ESM4": date(2024, 6, 21),
    "ESU4": date(2024, 9, 20),
    "ESZ4": date(2024, 12, 20),
}


def _front_month_volume(index: pd.DatetimeIndex, last_trade: date, peak: float) -> list[float]:
    """Volume that peaks at a contract's last trade and tapers away — front-month
    liquidity.  Each liquid contract is the volume leader near its own expiry, so the
    Liquid Cycle keeps them all; a serial uses a low peak and so never leads."""
    last = pd.Timestamp(last_trade)
    return [
        max(10.0, peak - (len(pd.bdate_range(min(day, last), max(day, last))) - 1))
        for day in index
    ]


def _leg_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    close = [_BASIS[symbol] + offset for offset in range(len(index))]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1.0 for value in close],
            "Low": [value - 1.0 for value in close],
            "Close": close,
            "Volume": _front_month_volume(index, _ES_LAST_TRADE[symbol], 1000.0),
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


def _es_three(root: str, start: date, end: date) -> list[DatedContract]:
    return [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
    ]


def test_databento_pull_does_not_require_bars_past_a_rolled_off_contract_expiry(tmp_path) -> None:
    """Regression (aegis-rd-lqz): the per-leg overlap buffer must not demand bars
    from a *rolled-off* contract past its last trade.

    The chain fetches each leg over ``[roll-14d, roll+14d]`` so adjacent contracts
    overlap on the seam, but a real provider returns nothing past a contract's last
    trade.  The coverage admission used to require the whole buffered window, so the
    dead tail of every rolled-off contract (here ESH4 after 2024-03-15, demanded
    through ~2024-03-22) aborted the pull.  Required coverage must be clamped to the
    contract's tradeable span; the still-active front contract (ESU4) carries the
    window edge.
    """
    ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    # ESH4/ESM4 roll off mid-window: a real provider has no bars past their last
    # trade.  ESU4 is the front contract at the window edge and still trades.
    rolled_off = {"ESH4": date(2024, 3, 15), "ESM4": date(2024, 6, 21)}

    def expiry_truncated_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        return _leg_bars(symbol, start, min(end, rolled_off.get(symbol, end)))

    request = NativeBarsRequest(
        refs=(ref,),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-01-02",
        end="2024-10-01",  # past ESU4's expiry so all three contracts are in the chain
        calendar=TradingCalendar.XNYS,
    )
    pull_databento_futures_bars(
        request, fetcher=expiry_truncated_fetch, contract_calendar=_es_three, store_dir=tmp_path
    )
    frames = read_native_bars(
        (ref,), arrays=("Close",), timeframe="1D",
        start="2024-01-02", end="2024-10-01", store_dir=tmp_path, calendar=TradingCalendar.XNYS,
    )
    assert not frames[ref]["Close"].isna().any()


def test_databento_pull_covers_through_end_via_the_front_at_end_contract(tmp_path) -> None:
    """Regression (aegis-rd-vv6): when the request end falls mid-contract — past the
    last *expiring* contract but inside the life of the next — the chain must include
    the contract front at end so a leg covers ``[last expiry, end]``.

    Every leg is truncated at its real last trade (as a provider returns nothing past
    expiry).  The chain used to select only contracts expiring within the window, so
    ESZ4 — front at the 2024-10-01 edge, expiring 2024-12-20 — was dropped and ESU4
    became the final leg; its window ran to ``end``, demanding bars past ESU4's
    2024-09-20 expiry and aborting the pull.  ESZ4 must carry the window edge instead.
    """
    ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    last_trade = {
        contract.symbol: contract.last_trade
        for contract in _es_calendar("ES", date(2024, 1, 2), date(2024, 10, 1))
    }

    def expiry_truncated_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        return _leg_bars(symbol, start, min(end, last_trade[symbol]))

    request = NativeBarsRequest(
        refs=(ref,),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-01-02",
        end="2024-10-01",  # past ESU4's 2024-09-20 expiry, mid-ESZ4 life
        calendar=TradingCalendar.XNYS,
    )
    pull_databento_futures_bars(
        request, fetcher=expiry_truncated_fetch, contract_calendar=_es_calendar, store_dir=tmp_path
    )
    frames = read_native_bars(
        (ref,), arrays=("Close",), timeframe="1D",
        start="2024-01-02", end="2024-10-01", store_dir=tmp_path, calendar=TradingCalendar.XNYS,
    )
    assert not frames[ref]["Close"].isna().any()


def test_databento_pull_tolerates_a_contract_non_print_on_an_xnys_day(tmp_path) -> None:
    """Regression (aegis-rd-voy): a futures contract need not print on every XNYS day
    within its tradeable life.  Thin/serial months and non-XNYS venue holidays
    legitimately skip sessions, so a bar absent on an XNYS day inside a contract's
    life is a non-trading day, not missing data.  The per-leg coverage admission
    imposed a rigid XNYS required-day grid and aborted on the first absent day (here
    ESM4 not printing on 2024-05-08, an interior XNYS trading day).
    """
    ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    skipped = pd.Timestamp("2024-05-08")  # an interior XNYS day ESM4 simply did not print

    def thin_contract_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        bars = _leg_bars(symbol, start, end)
        if symbol == "ESM4":
            bars = bars.drop(index=skipped, errors="ignore")
        return bars

    pull_databento_futures_bars(
        _request(ref), fetcher=thin_contract_fetch, contract_calendar=_es_calendar, store_dir=tmp_path
    )
    frames = read_native_bars(
        (ref,), arrays=("Close",), timeframe="1D",
        start="2024-01-02", end="2025-01-01", store_dir=tmp_path, calendar=TradingCalendar.XNYS,
    )
    assert not frames[ref]["Close"].isna().any()
    assert skipped not in frames[ref].index


def test_databento_pull_tolerates_a_thin_contract_that_stops_before_its_expiry(tmp_path) -> None:
    """Regression (aegis-rd-voy, surfaced by the live GC pull): a thin/serial contract
    can stop printing days before its definitional expiry.  A non-final leg's window
    runs to its expiry (the lqz clamp), but its last real bar is earlier, so the
    ``[last bar, expiry]`` tail must be tolerated — it is past where the continuous
    series uses the leg (the roll seam is placed by the snapped common trading day).
    Live symptom: ``GLBX.MDP3:GCK4: missing expected 1D bar on 2024-05-29`` (GCK4, the
    May gold serial, stopped trading before its 2024-05 expiry).
    """
    ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    # ESM4 is a mid-chain leg (expiry 2024-06-21) that stops trading 2024-06-10, well
    # before its expiry — as a thin serial does.
    stops_early = {"ESM4": date(2024, 6, 10)}

    def thin_contract_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        return _leg_bars(symbol, start, min(end, stops_early.get(symbol, end)))

    request = NativeBarsRequest(
        refs=(ref,),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-01-02",
        end="2024-10-01",  # ESZ4 carries the window edge; ESM4 is mid-chain
        calendar=TradingCalendar.XNYS,
    )
    pull_databento_futures_bars(
        request, fetcher=thin_contract_fetch, contract_calendar=_es_calendar, store_dir=tmp_path
    )
    frames = read_native_bars(
        (ref,), arrays=("Close",), timeframe="1D",
        start="2024-01-02", end="2024-10-01", store_dir=tmp_path, calendar=TradingCalendar.XNYS,
    )
    assert not frames[ref]["Close"].isna().any()


_GC_LAST_TRADE = {
    "GCK4": date(2024, 5, 28),  # May serial
    "GCM4": date(2024, 6, 26),  # June liquid
    "GCN4": date(2024, 7, 29),  # July serial
    "GCQ4": date(2024, 8, 28),  # August liquid
}
_GC_BASIS = {"GCK4": 2300.0, "GCM4": 2320.0, "GCN4": 2340.0, "GCQ4": 2360.0}
_GC_LIQUID = {"GCM4", "GCQ4"}


def _gc_calendar(root: str, start: date, end: date) -> list[DatedContract]:
    return [DatedContract(symbol, last) for symbol, last in _GC_LAST_TRADE.items()]


def _gc_leg_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    close = [_GC_BASIS[symbol] + offset for offset in range(len(index))]
    peak = 1000.0 if symbol in _GC_LIQUID else 60.0
    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1.0 for value in close],
            "Low": [value - 1.0 for value in close],
            "Close": close,
            "Volume": _front_month_volume(index, _GC_LAST_TRADE[symbol], peak),
        },
        index=index,
    )


def test_databento_pull_stores_only_the_liquid_cycle_excluding_serials(tmp_path) -> None:
    """Slice 1 acceptance: a GC pull over summer 2024 holds the liquid June/August
    contracts and never rolls through the thin May/July serials.  The serials are still
    probed and retained as cached-but-unused Raw Futures Legs, but they are absent from
    the continuous derivation (``raw_legs``)."""
    ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-05-01",
        end="2024-08-01",
        calendar=TradingCalendar.XNYS,
    )

    result = pull_databento_futures_bars(
        request, fetcher=_gc_leg_bars, contract_calendar=_gc_calendar, store_dir=tmp_path
    )
    frames = read_native_bars(
        (ref,), arrays=("Close",), timeframe="1D",
        start="2024-05-01", end="2024-08-01", store_dir=tmp_path, calendar=TradingCalendar.XNYS,
    )

    assert tuple(leg.symbol for leg in result.raw_legs) == ("GCM4", "GCQ4")
    assert raw_futures_leg_path("GLBX.MDP3", "GCK4", "1D", store_dir=tmp_path).exists()
    assert raw_futures_leg_path("GLBX.MDP3", "GCN4", "1D", store_dir=tmp_path).exists()
    assert not frames[ref]["Close"].isna().any()


def test_databento_pull_liquid_cycle_tolerates_a_liquid_leg_non_print(tmp_path) -> None:
    """Slice 2 (aegis-rd-voy retained): after liquidity filtering, the liquid front
    contract may still skip a session within its life (a venue holiday / non-print); the
    pull tolerates it rather than aborting.  This is the very symptom voy fixed — now on
    the liquid GCM4 that covers May, not the excluded GCK4 serial that triggered it."""
    ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    skipped = pd.Timestamp("2024-05-08")  # an interior XNYS day GCM4 simply does not print

    def thin_liquid_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        bars = _gc_leg_bars(symbol, start, end)
        if symbol == "GCM4":
            bars = bars.drop(index=skipped, errors="ignore")
        return bars

    request = NativeBarsRequest(
        refs=(ref,),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-05-01",
        end="2024-08-01",
        calendar=TradingCalendar.XNYS,
    )
    result = pull_databento_futures_bars(
        request, fetcher=thin_liquid_fetch, contract_calendar=_gc_calendar, store_dir=tmp_path
    )
    frames = read_native_bars(
        (ref,), arrays=("Close",), timeframe="1D",
        start="2024-05-01", end="2024-08-01", store_dir=tmp_path, calendar=TradingCalendar.XNYS,
    )

    assert tuple(leg.symbol for leg in result.raw_legs) == ("GCM4", "GCQ4")
    assert not frames[ref]["Close"].isna().any()
    assert skipped not in frames[ref].index


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

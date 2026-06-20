"""OS-global parquet store (aegis-data)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.calendars import TradingCalendar, business_day_offset
from aegis_data.store import (
    FxPair,
    NATIVE_OHLCV_ARRAYS,
    StoreCoverageError,
    assert_native_bar_coverage,
    cached_fetcher,
    data_dir,
    ListedAdjustmentPolicy,
    NativeBarsRequest,
    merge_native_bars,
    native_bars_path,
    read_fx_history,
    read_native_bars,
    replace_native_bars,
    write_fx_history,
    write_native_bars,
)


def test_cached_fetcher_writes_then_reads_from_store(tmp_path) -> None:
    calls: list[str] = []

    def base(symbol: str, start: date, end: date) -> pd.DataFrame:
        calls.append(symbol)
        idx = pd.bdate_range(start, end)
        return pd.DataFrame({"Close": [1.0] * len(idx)}, index=idx)

    fetch = cached_fetcher(base, dataset="GLBX.MDP3", store_dir=tmp_path)

    first = fetch("ESZ4", date(2024, 1, 1), date(2024, 3, 1))
    second = fetch("ESZ4", date(2024, 1, 1), date(2024, 3, 1))

    assert calls == ["ESZ4"]  # provider hit once
    pd.testing.assert_frame_equal(first, second)
    assert (tmp_path / "futures" / "GLBX.MDP3" / "ESZ4_2024-01-01_2024-03-01.parquet").exists()


def test_data_dir_respects_env_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def _listed_bars() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [100.0, 101.0, 102.0, 103.0, 104.0],
            "low": [100.0, 101.0, 102.0, 103.0, 104.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1000, 1100, 1200, 1300, 1400],
        },
        index=index,
    )


def test_listed_native_bar_identity_includes_adjustment_policy(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")

    path = native_bars_path(
        ref,
        "1D",
        listed_adjustment=ListedAdjustmentPolicy.RAW,
        store_dir=tmp_path,
    )

    assert path == tmp_path / "listed" / "BBG000B9XRY4" / "bars" / "raw" / "1D.parquet"


def test_native_bar_store_read_returns_provider_free_listed_frames(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    write_native_bars(ref, "1D", _listed_bars(), store_dir=tmp_path)

    frames = read_native_bars(
        (ref,),
        arrays=("close", "volume"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )

    assert tuple(frames) == (ref,)
    assert list(frames[ref].columns) == ["close", "volume"]
    assert frames[ref]["close"].tolist() == [101.0, 102.0, 103.0]


def test_native_bar_store_read_fails_closed_on_missing_listed_coverage(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    gapped = _listed_bars().drop(pd.Timestamp("2024-01-03"))
    write_native_bars(ref, "1D", gapped, store_dir=tmp_path)

    with pytest.raises(StoreCoverageError) as exc:
        read_native_bars(
            (ref,),
            arrays=("close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar=TradingCalendar.XNYS,
            store_dir=tmp_path,
        )

    assert "BBG000B9XRY4" in str(exc.value)
    assert "2024-01-03" in str(exc.value)


def test_native_bar_store_read_does_not_require_exchange_holiday_bars(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [100.0, 101.0],
            "low": [100.0, 101.0],
            "close": [100.0, 101.0],
            "volume": [1000, 1100],
        },
        index=pd.DatetimeIndex(["2024-03-28", "2024-04-01"]),
    )
    write_native_bars(ref, "1D", bars, store_dir=tmp_path)

    # Good Friday 2024-03-29 is an XNYS holiday, so XNYS must not expect a bar there.
    frames = read_native_bars(
        (ref,),
        arrays=("close",),
        timeframe="1D",
        start="2024-03-28",
        end="2024-04-02",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )

    assert frames[ref]["close"].tolist() == [100.0, 101.0]


def _cme_futures_frame(days: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({array: [1.0] * len(days) for array in NATIVE_OHLCV_ARRAYS}, index=days)


def test_continuous_futures_coverage_tolerates_interior_but_requires_window_edges() -> None:
    # aegis-rd-voy: the assembled continuous futures series tolerates interior
    # non-prints (thin/serial months, venue holidays) but must span the request
    # window: an uncovered prefix (it does not reach the window start) is a real gap,
    # so the series is not silently truncated.  (Contrast the listed path above, where
    # an interior gap also fails closed — a listed instrument trades every session.)
    ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    sessions = pd.date_range(
        "2024-05-01", "2024-05-31", freq=business_day_offset(TradingCalendar.CME)
    )

    assert_native_bar_coverage(  # interior non-print tolerated
        ref,
        _cme_futures_frame(sessions.drop(pd.Timestamp("2024-05-08"))),
        arrays=NATIVE_OHLCV_ARRAYS,
        timeframe="1D",
        start="2024-05-01",
        end="2024-06-01",
        calendar=TradingCalendar.CME,
    )

    with pytest.raises(StoreCoverageError, match="missing expected"):
        assert_native_bar_coverage(  # uncovered window prefix is still a gap
            ref,
            _cme_futures_frame(sessions[5:]),
            arrays=NATIVE_OHLCV_ARRAYS,
            timeframe="1D",
            start="2024-05-01",
            end="2024-06-01",
            calendar=TradingCalendar.CME,
        )


def test_intraday_store_read_fails_closed_on_missing_mid_session_bar(tmp_path) -> None:
    # XNYS 15min RTH session 2024-01-02 09:30..15:45, minus one mid-session bar.
    ref = ListedRef("BBG000B9XRY4")
    session = pd.date_range("2024-01-02 09:30", "2024-01-02 16:00", freq="15min", inclusive="left")
    gapped = session.delete(list(session).index(pd.Timestamp("2024-01-02 11:00")))
    bars = pd.DataFrame({"close": [float(i) for i in range(len(gapped))]}, index=gapped)
    write_native_bars(ref, "15min", bars, store_dir=tmp_path)

    with pytest.raises(StoreCoverageError) as exc:
        read_native_bars(
            (ref,),
            arrays=("close",),
            timeframe="15min",
            start="2024-01-02 09:30",
            end="2024-01-02 16:00",
            calendar=TradingCalendar.XNYS,
            store_dir=tmp_path,
        )

    assert "11:00" in str(exc.value)


def test_intraday_store_read_passes_with_a_complete_session(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    session = pd.date_range("2024-01-02 09:30", "2024-01-02 16:00", freq="15min", inclusive="left")
    bars = pd.DataFrame({"close": [float(i) for i in range(len(session))]}, index=session)
    write_native_bars(ref, "15min", bars, store_dir=tmp_path)

    frames = read_native_bars(
        (ref,),
        arrays=("close",),
        timeframe="15min",
        start="2024-01-02 09:30",
        end="2024-01-02 16:00",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )

    assert len(frames[ref]) == 26


@pytest.mark.parametrize(
    "session_day",
    [
        pytest.param("2024-07-03", id="july-third"),
        pytest.param("2024-11-29", id="day-after-thanksgiving"),
        pytest.param("2024-12-24", id="christmas-eve"),
    ],
)
def test_intraday_store_read_accepts_xnys_standard_early_closes(tmp_path, session_day: str) -> None:
    ref = ListedRef("BBG000B9XRY4")
    session = pd.date_range(
        f"{session_day} 09:30",
        f"{session_day} 13:00",
        freq="15min",
        inclusive="left",
    )
    bars = pd.DataFrame({"close": [float(i) for i in range(len(session))]}, index=session)
    write_native_bars(ref, "15min", bars, store_dir=tmp_path)

    frames = read_native_bars(
        (ref,),
        arrays=("close",),
        timeframe="15min",
        start=f"{session_day} 09:30",
        end=f"{session_day} 16:00",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )

    assert len(frames[ref]) == 14
    assert frames[ref].index[-1] == pd.Timestamp(f"{session_day} 12:45")


def test_merge_native_bars_keeps_existing_covered_history_on_overlap(tmp_path) -> None:
    # Additive merge is idempotent: a re-Pull of overlapping dates must not rewrite
    # already-admitted bars.
    ref = ListedRef("BBG000B9XRY4")
    write_native_bars(ref, "1D", _listed_bars(), store_dir=tmp_path)
    restated = _listed_bars()
    restated["close"] = restated["close"] + 1000.0

    merge_native_bars(ref, "1D", restated, store_dir=tmp_path)

    frames = read_native_bars(
        (ref,),
        arrays=("close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )
    assert frames[ref]["close"].tolist() == [101.0, 102.0, 103.0]


def test_replace_native_bars_overwrites_overlap_and_keeps_outside(tmp_path) -> None:
    # Replace wins across its own span (re-derived history) but retains bars outside it.
    ref = ListedRef("BBG000B9XRY4")
    write_native_bars(ref, "1D", _listed_bars(), store_dir=tmp_path)
    replacement = pd.DataFrame(
        {
            "open": [9990.0, 9991.0],
            "high": [9990.0, 9991.0],
            "low": [9990.0, 9991.0],
            "close": [9990.0, 9991.0],
            "volume": [1, 1],
        },
        index=pd.DatetimeIndex(["2024-01-03", "2024-01-04"]),
    )

    replace_native_bars(ref, "1D", replacement, store_dir=tmp_path)

    frames = read_native_bars(
        (ref,),
        arrays=("close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )
    # 2024-01-02 retained from the original; 2024-01-03/04 overwritten.
    assert frames[ref]["close"].tolist() == [101.0, 9990.0, 9991.0]


def test_native_bars_request_requires_a_trading_calendar() -> None:
    # No silent default: a Store Read must name its expected-bar calendar.
    with pytest.raises(TypeError):
        NativeBarsRequest(
            refs=(ListedRef("BBG000B9XRY4"),),
            arrays=("Close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
        )


def test_store_read_fails_closed_on_unknown_calendar(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    write_native_bars(ref, "1D", _listed_bars(), store_dir=tmp_path)

    with pytest.raises(ValueError, match="unsupported trading calendar"):
        read_native_bars(
            (ref,),
            arrays=("close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar="lse",
            store_dir=tmp_path,
        )


def test_fx_history_weekday_calendar_expects_a_us_holiday_weekday(tmp_path) -> None:
    # MLK Day 2024-01-15 (Mon) is an XNYS holiday, but FX trades that weekday, so
    # a WEEKDAY calendar must expect a rate there and fail closed when it is absent.
    pair = FxPair("EUR", "USD")
    rates = pd.Series(
        [1.10, 1.11, 1.12],
        index=pd.DatetimeIndex(["2024-01-12", "2024-01-16", "2024-01-17"]),
    )
    write_fx_history(pair, "1D", rates, store_dir=tmp_path)

    with pytest.raises(StoreCoverageError) as exc:
        read_fx_history(
            (pair,),
            timeframe="1D",
            start="2024-01-12",
            end="2024-01-18",
            calendar=TradingCalendar.WEEKDAY,
            store_dir=tmp_path,
        )

    assert "2024-01-15" in str(exc.value)


def test_fx_history_store_read_returns_provider_free_rates(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    index = pd.bdate_range("2024-01-01", periods=5)
    rates = pd.Series([1.10, 1.11, 1.12, 1.13, 1.14], index=index)
    write_fx_history(pair, "1D", rates, store_dir=tmp_path)

    history = read_fx_history(
        (pair,),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.WEEKDAY,
        store_dir=tmp_path,
    )

    assert tuple(history) == (pair,)
    assert history[pair].tolist() == [1.11, 1.12, 1.13]


def test_fx_history_store_read_fails_closed_on_missing_coverage(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    index = pd.bdate_range("2024-01-01", periods=5).delete(2)
    rates = pd.Series([1.10, 1.11, 1.13, 1.14], index=index)
    write_fx_history(pair, "1D", rates, store_dir=tmp_path)

    with pytest.raises(StoreCoverageError) as exc:
        read_fx_history(
            (pair,),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar=TradingCalendar.WEEKDAY,
            store_dir=tmp_path,
        )

    assert "EUR/USD" in str(exc.value)
    assert "2024-01-03" in str(exc.value)

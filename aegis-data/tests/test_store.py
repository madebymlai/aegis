"""OS-global parquet store (aegis-data)."""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.calendars import TradingCalendar, business_day_offset
from aegis_data.store import (
    CoveredWindow,
    CoverageGap,
    FxPair,
    HistoricalStore,
    NATIVE_OHLCV_ARRAYS,
    StoreAdmissionError,
    StoreCoverageError,
    WriteMode,
    data_dir,
    NativeBarsRequest,
    RawFuturesLeg,
)


def test_data_dir_respects_env_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def _listed_window(
    *,
    start: str = "2024-01-02",
    end: str = "2024-01-05",
    arrays: tuple[str, ...] = ("close",),
) -> CoveredWindow:
    return CoveredWindow(
        timeframe="1D",
        start=start,
        end=end,
        arrays=arrays,
        calendar=TradingCalendar.XNYS,
    )


def _fx_window(
    *,
    start: str = "2024-01-02",
    end: str = "2024-01-05",
) -> CoveredWindow:
    return CoveredWindow(
        timeframe="1D",
        start=start,
        end=end,
        arrays=("rate",),
        calendar=TradingCalendar.WEEKDAY,
    )


def _futures_window(
    *,
    start: str = "2024-01-12",
    end: str = "2024-01-17",
) -> CoveredWindow:
    return CoveredWindow(
        timeframe="1D",
        start=start,
        end=end,
        arrays=("Close",),
        calendar=TradingCalendar.XNYS,
    )


def test_historical_store_write_overwrite_seeds_and_reads_listed_frame(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window(arrays=("close", "volume"))

    store.write(ref, _listed_bars(), window, mode=WriteMode.OVERWRITE)
    frame = store.read(ref, window)

    assert list(frame.columns) == ["close", "volume"]
    assert frame["close"].tolist() == [101.0, 102.0, 103.0]


def test_historical_store_defaults_to_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))

    store = HistoricalStore()

    assert store.root == tmp_path


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


def test_historical_store_write_requires_mode(tmp_path) -> None:
    store = HistoricalStore(tmp_path)
    window = _listed_window()

    with pytest.raises(TypeError):
        store.write(ListedRef("BBG000B9XRY4"), _listed_bars(), window)


def test_historical_store_read_fails_closed_on_missing_file(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()

    with pytest.raises(StoreCoverageError) as exc:
        store.read(ref, window)

    assert "missing expected 1D bar on 2024-01-02" in str(exc.value)


def test_historical_store_read_fails_closed_on_missing_array(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    store.write(ref, _listed_bars(), _listed_window(), mode=WriteMode.OVERWRITE)
    window = _listed_window(arrays=("adj_close",))

    with pytest.raises(StoreCoverageError) as exc:
        store.read(ref, window)

    assert "missing arrays ['adj_close']" in str(exc.value)


def test_historical_store_read_fails_closed_on_nan(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()
    bars = _listed_bars()
    bars.loc[pd.Timestamp("2024-01-03"), "close"] = float("nan")
    store.write(ref, bars, window, mode=WriteMode.OVERWRITE)

    with pytest.raises(StoreCoverageError) as exc:
        store.read(ref, window)

    assert "missing expected 1D bar on 2024-01-03" in str(exc.value)


def test_historical_store_write_merge_keeps_existing_overlap(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()
    store.write(ref, _listed_bars(), window, mode=WriteMode.OVERWRITE)
    restated = _listed_bars()
    restated["close"] = restated["close"] + 1000.0

    store.write(ref, restated, window, mode=WriteMode.MERGE)
    frame = store.read(ref, window)

    assert frame["close"].tolist() == [101.0, 102.0, 103.0]


def test_historical_store_write_replace_overwrites_span_and_keeps_outside(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()
    store.write(ref, _listed_bars(), window, mode=WriteMode.OVERWRITE)
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

    store.write(ref, replacement, window, mode=WriteMode.REPLACE)
    frame = store.read(ref, window)

    assert frame["close"].tolist() == [101.0, 9990.0, 9991.0]


def test_historical_store_write_overwrite_replaces_full_slice(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()
    store.write(ref, _listed_bars(), window, mode=WriteMode.OVERWRITE)
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

    store.write(ref, replacement, window, mode=WriteMode.OVERWRITE)
    frame = store.read(ref, _listed_window(start="2024-01-03"))
    gaps = store.coverage_gaps(ref, window)

    assert frame["close"].tolist() == [9990.0, 9991.0]
    assert gaps == (CoverageGap(start=pd.Timestamp("2024-01-02"), end=pd.Timestamp("2024-01-03")),)


def test_historical_store_fx_history_uses_rate_column_frame(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    store = HistoricalStore(tmp_path)
    window = _fx_window()
    rates = pd.DataFrame(
        {"rate": [1.10, 1.11, 1.12, 1.13, 1.14]},
        index=pd.bdate_range("2024-01-01", periods=5),
    )

    store.write(pair, rates, window, mode=WriteMode.OVERWRITE)
    frame = store.read(pair, window)

    assert list(frame.columns) == ["rate"]
    assert frame["rate"].tolist() == [1.11, 1.12, 1.13]


def test_historical_store_futures_read_uses_dataset_calendar_for_window_edges(
    tmp_path,
) -> None:
    ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    store = HistoricalStore(tmp_path)
    window = _futures_window()
    store.write(
        ref,
        _cme_futures_frame(pd.DatetimeIndex(["2024-01-12", "2024-01-16"])),
        window,
        mode=WriteMode.OVERWRITE,
    )

    frame = store.read(ref, window)
    with pytest.raises(StoreCoverageError) as exc:
        store.read(ref, _futures_window(start="2024-01-15"))

    assert frame.index.tolist() == [pd.Timestamp("2024-01-12"), pd.Timestamp("2024-01-16")]
    assert "2024-01-15" in str(exc.value)


def test_historical_store_futures_adjustments_do_not_collide(tmp_path) -> None:
    ratio_ref = FuturesRef(
        "GC",
        "GLBX.MDP3",
        roll_rule="calendar",
        adjustment="backward_ratio",
    )
    raw_ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="unadjusted")
    store = HistoricalStore(tmp_path)
    window = _futures_window()
    ratio_bars = _cme_futures_frame(pd.DatetimeIndex(["2024-01-12", "2024-01-16"]))
    raw_bars = ratio_bars.copy()
    raw_bars["Close"] = 2.0

    store.write(ratio_ref, ratio_bars, window, mode=WriteMode.OVERWRITE)
    store.write(raw_ref, raw_bars, window, mode=WriteMode.OVERWRITE)

    assert store.read(ratio_ref, window)["Close"].tolist() == [1.0, 1.0]
    assert store.read(raw_ref, window)["Close"].tolist() == [2.0, 2.0]


def test_historical_store_coverage_gaps_match_store_coverage(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()
    store.write(
        ref,
        _listed_bars().drop(pd.Timestamp("2024-01-03")),
        window,
        mode=WriteMode.OVERWRITE,
    )

    gaps = store.coverage_gaps(ref, window)

    assert gaps == (CoverageGap(start=pd.Timestamp("2024-01-03"), end=pd.Timestamp("2024-01-04")),)


def test_covered_window_narrows_to_one_gap_for_admission(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()
    narrowed = window.narrowed_to(
        CoverageGap(start=pd.Timestamp("2024-01-03"), end=pd.Timestamp("2024-01-04"))
    )

    store.assert_admissible(ref, _listed_bars().loc[["2024-01-03"]], narrowed)

    assert narrowed.timeframe == window.timeframe
    assert narrowed.start == pd.Timestamp("2024-01-03")
    assert narrowed.end == pd.Timestamp("2024-01-04")
    assert narrowed.arrays == window.arrays
    assert narrowed.calendar == window.calendar
    assert narrowed.listed_adjustment == window.listed_adjustment


def test_historical_store_assert_admissible_raises_store_admission_error(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    window = _listed_window()

    with pytest.raises(StoreAdmissionError) as exc:
        store.assert_admissible(
            ref,
            _listed_bars().drop(pd.Timestamp("2024-01-03")),
            window,
        )

    assert "missing expected 1D bar on 2024-01-03" in str(exc.value)


def _cme_futures_frame(days: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({array: [1.0] * len(days) for array in NATIVE_OHLCV_ARRAYS}, index=days)


def test_historical_store_assert_admissible_tolerates_futures_interior_gaps() -> None:
    # aegis-rd-voy: the assembled continuous futures series tolerates interior
    # non-prints (thin/serial months, venue holidays) but must span the request
    # window: an uncovered prefix (it does not reach the window start) is a real gap,
    # so the series is not silently truncated.  (Contrast the listed path above, where
    # an interior gap also fails closed — a listed instrument trades every session.)
    ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    sessions = pd.date_range(
        "2024-05-01", "2024-05-31", freq=business_day_offset(TradingCalendar.CME)
    )
    store = HistoricalStore()
    window = CoveredWindow(
        timeframe="1D",
        start="2024-05-01",
        end="2024-06-01",
        arrays=NATIVE_OHLCV_ARRAYS,
        calendar=TradingCalendar.CME,
    )

    store.assert_admissible(
        ref,
        _cme_futures_frame(sessions.drop(pd.Timestamp("2024-05-08"))),
        window,
    )

    with pytest.raises(StoreAdmissionError, match="missing expected"):
        store.assert_admissible(
            ref,
            _cme_futures_frame(sessions[5:]),
            window,
        )


def test_historical_store_raw_leg_read_is_cold_tolerant(tmp_path) -> None:
    leg = RawFuturesLeg("GLBX.MDP3", "ESH4")
    store = HistoricalStore(tmp_path)
    window = CoveredWindow(
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        arrays=("Close", "Volume"),
        calendar=TradingCalendar.CONTINUOUS,
    )

    frame = store.read_leg(leg, window)

    pd.testing.assert_frame_equal(
        frame,
        pd.DataFrame(columns=["Close", "Volume"], index=pd.DatetimeIndex([])),
    )


def test_historical_store_raw_leg_merge_reads_slice_and_records_coverage(tmp_path) -> None:
    leg = RawFuturesLeg("GLBX.MDP3", "ESH4")
    store = HistoricalStore(tmp_path)
    window = CoveredWindow(
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-06",
        arrays=("Close", "Volume"),
        calendar=TradingCalendar.CONTINUOUS,
    )
    bars = pd.DataFrame(
        {
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1000, 1100, 1200, 1300],
        },
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )

    store.merge_leg(leg, bars, window)
    store.record_leg_coverage(leg, window)
    frame = store.read_leg(
        leg,
        CoveredWindow(
            timeframe="1D",
            start="2024-01-03",
            end="2024-01-05",
            arrays=("Close",),
            calendar=TradingCalendar.CONTINUOUS,
        ),
    )

    pd.testing.assert_frame_equal(
        frame,
        pd.DataFrame(
            {"Close": [101.5, 102.5]},
            index=pd.DatetimeIndex(["2024-01-03", "2024-01-04"]),
        ),
    )
    assert store.read_leg_coverage(leg, timeframe="1D") == (
        CoverageGap(start=pd.Timestamp("2024-01-02"), end=pd.Timestamp("2024-01-06")),
    )


def test_intraday_store_read_fails_closed_on_missing_mid_session_bar(tmp_path) -> None:
    # XNYS 15min RTH session 2024-01-02 09:30..15:45, minus one mid-session bar.
    ref = ListedRef("BBG000B9XRY4")
    session = pd.date_range("2024-01-02 09:30", "2024-01-02 16:00", freq="15min", inclusive="left")
    gapped = session.delete(list(session).index(pd.Timestamp("2024-01-02 11:00")))
    bars = pd.DataFrame({"close": [float(i) for i in range(len(gapped))]}, index=gapped)
    store = HistoricalStore(tmp_path)
    window = CoveredWindow(
        timeframe="15min",
        start="2024-01-02 09:30",
        end="2024-01-02 16:00",
        arrays=("close",),
        calendar=TradingCalendar.XNYS,
    )
    store.write(ref, bars, window, mode=WriteMode.OVERWRITE)

    with pytest.raises(StoreCoverageError) as exc:
        store.read(ref, window)

    assert "11:00" in str(exc.value)


def test_intraday_store_read_passes_with_a_complete_session(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    session = pd.date_range("2024-01-02 09:30", "2024-01-02 16:00", freq="15min", inclusive="left")
    bars = pd.DataFrame({"close": [float(i) for i in range(len(session))]}, index=session)
    store = HistoricalStore(tmp_path)
    window = CoveredWindow(
        timeframe="15min",
        start="2024-01-02 09:30",
        end="2024-01-02 16:00",
        arrays=("close",),
        calendar=TradingCalendar.XNYS,
    )
    store.write(ref, bars, window, mode=WriteMode.OVERWRITE)
    frame = store.read(ref, window)

    assert len(frame) == 26


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
    store = HistoricalStore(tmp_path)
    window = CoveredWindow(
        timeframe="15min",
        start=f"{session_day} 09:30",
        end=f"{session_day} 16:00",
        arrays=("close",),
        calendar=TradingCalendar.XNYS,
    )
    store.write(ref, bars, window, mode=WriteMode.OVERWRITE)
    frame = store.read(ref, window)

    assert len(frame) == 14
    assert frame.index[-1] == pd.Timestamp(f"{session_day} 12:45")


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
    with pytest.raises(ValueError, match="unsupported trading calendar"):
        CoveredWindow(
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            arrays=("close",),
            calendar="lse",
        )

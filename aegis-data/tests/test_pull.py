"""Covered Pull loop seam tests."""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime import ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.pull import FetchWindow, pull
from aegis_data.store import (
    CoveredWindow,
    CoverageGap,
    HistoricalStore,
    StoreAdmissionError,
    WriteMode,
)

_ARRAYS = ("Open", "High", "Low", "Close", "Volume")


def _window(
    *,
    start: str = "2024-01-02",
    end: str = "2024-01-05",
    arrays: tuple[str, ...] = _ARRAYS,
) -> CoveredWindow:
    return CoveredWindow(
        timeframe="1D",
        start=start,
        end=end,
        arrays=arrays,
        calendar=TradingCalendar.XNYS,
    )


def _bars(dates: tuple[str, ...], close: tuple[float, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": [1000 + offset for offset, _ in enumerate(close)],
        },
        index=pd.DatetimeIndex(dates),
    )


def _seed(
    store: HistoricalStore,
    ref: ListedRef,
    dates: tuple[str, ...],
    close: tuple[float, ...],
) -> None:
    store.write(
        ref,
        _bars(dates, close),
        _window(
            start=dates[0],
            end=str((pd.Timestamp(dates[-1]) + pd.Timedelta(days=1)).date()),
        ),
        mode=WriteMode.OVERWRITE,
    )


def test_pull_fills_uncovered_gap_with_fetch_window(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    _seed(store, ref, ("2024-01-02",), (100.0,))
    calls: list[tuple[str | pd.Timestamp, str | pd.Timestamp, tuple[str, ...]]] = []

    def fetch(window: FetchWindow) -> pd.DataFrame:
        calls.append((window.start, window.end, tuple(window.arrays)))
        return _bars(
            ("2024-01-03", "2024-01-04"),
            (101.0, 102.0),
        )

    pull(ref, _window(), store=store, fetch=fetch)
    frame = store.read(ref, _window(arrays=("Close",)))

    assert calls == [
        (pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05"), _ARRAYS)
    ]
    assert frame["Close"].tolist() == [100.0, 101.0, 102.0]
    assert store.coverage_gaps(ref, _window()) == ()


def test_pull_merge_keeps_existing_overlap(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    _seed(store, ref, ("2024-01-02",), (100.0,))

    pull(
        ref,
        _window(),
        store=store,
        fetch=lambda _window: _bars(
            ("2024-01-02", "2024-01-03", "2024-01-04"),
            (999.0, 101.0, 102.0),
        ),
    )
    frame = store.read(ref, _window(arrays=("Close",)))

    assert frame["Close"].tolist() == [100.0, 101.0, 102.0]


def test_pull_noops_when_window_is_already_covered(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    _seed(
        store,
        ref,
        ("2024-01-02", "2024-01-03", "2024-01-04"),
        (100.0, 101.0, 102.0),
    )

    pull(
        ref,
        _window(),
        store=store,
        fetch=lambda _window: pytest.fail("pull fetched an already-covered window"),
    )
    frame = store.read(ref, _window(arrays=("Close",)))

    assert frame["Close"].tolist() == [100.0, 101.0, 102.0]


def test_pull_rejects_insufficient_frame_before_writing(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)

    with pytest.raises(StoreAdmissionError, match="2024-01-03"):
        pull(
            ref,
            _window(),
            store=store,
            fetch=lambda _window: _bars(("2024-01-02",), (100.0,)),
        )

    assert store.coverage_gaps(ref, _window()) == (
        CoverageGap(start=pd.Timestamp("2024-01-02"), end=pd.Timestamp("2024-01-05")),
    )

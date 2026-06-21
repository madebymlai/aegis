"""Coverage-aware Raw Futures Leg cache."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from aegis_data.raw_leg_cache import RawLegCache, raw_leg_ports
from aegis_data.store import RawFuturesLeg, StoreCoverageError, merge_raw_futures_leg


def _bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="D")
    base = float(sum(ord(char) for char in symbol))
    close = [base + offset for offset in range(len(index))]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1.0 for value in close],
            "Low": [value - 1.0 for value in close],
            "Close": close,
            "Volume": [1000.0 + offset for offset in range(len(index))],
        },
        index=index,
    )


class _Provider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []

    def __call__(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        self.calls.append((symbol, start, end))
        return _bars(symbol, start, end)


def test_raw_leg_cache_cold_leg_pulls_once_and_returns_requested_window(tmp_path) -> None:
    provider = _Provider()
    cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        store_dir=tmp_path,
    )

    frame = cache.fetch("ESH4", date(2024, 1, 2), date(2024, 1, 5))

    assert provider.calls == [("ESH4", date(2024, 1, 2), date(2024, 1, 5))]
    assert list(frame.index) == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-01-04"),
        pd.Timestamp("2024-01-05"),
    ]
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_raw_leg_cache_sub_window_of_cached_leg_pulls_zero(tmp_path) -> None:
    provider = _Provider()
    cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        store_dir=tmp_path,
    )
    cache.fetch("ESH4", date(2024, 1, 2), date(2024, 1, 5))
    provider.calls.clear()

    frame = cache.fetch("ESH4", date(2024, 1, 3), date(2024, 1, 4))

    assert provider.calls == []
    assert list(frame.index) == [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04")]


def test_raw_leg_cache_wider_window_fetches_only_uncovered_edge(tmp_path) -> None:
    provider = _Provider()
    leg = RawFuturesLeg("GLBX.MDP3", "ESH4")
    merge_raw_futures_leg(
        leg,
        "1D",
        _bars("ESH4", date(2024, 1, 3), date(2024, 1, 5)),
        required_arrays=("Open", "High", "Low", "Close", "Volume"),
        store_dir=tmp_path,
    )
    cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        store_dir=tmp_path,
    )

    frame = cache.fetch("ESH4", date(2024, 1, 1), date(2024, 1, 5))

    assert provider.calls == [("ESH4", date(2024, 1, 1), date(2024, 1, 2))]
    assert list(frame.index) == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-01-04"),
        pd.Timestamp("2024-01-05"),
    ]


def test_raw_leg_cache_probe_then_deliverable_reuses_one_pull(tmp_path) -> None:
    provider = _Provider()
    cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        store_dir=tmp_path,
    )

    cache.fetch("ESH4", date(2024, 1, 1), date(2024, 1, 10))
    deliverable = cache.fetch("ESH4", date(2024, 1, 3), date(2024, 1, 5))

    assert provider.calls == [("ESH4", date(2024, 1, 1), date(2024, 1, 10))]
    pd.testing.assert_frame_equal(
        deliverable,
        pd.DataFrame(
            {
                "Open": [278.0, 279.0, 280.0],
                "High": [279.0, 280.0, 281.0],
                "Low": [277.0, 278.0, 279.0],
                "Close": [278.0, 279.0, 280.0],
                "Volume": [1002.0, 1003.0, 1004.0],
            },
            index=pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05"]),
        ),
    )


def test_raw_leg_cache_interior_sparsity_is_not_re_pulled(tmp_path) -> None:
    provider = _Provider()
    leg = RawFuturesLeg("GLBX.MDP3", "ESH4")
    sparse = _bars("ESH4", date(2024, 1, 1), date(2024, 1, 5)).drop(
        [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")]
    )
    merge_raw_futures_leg(
        leg,
        "1D",
        sparse,
        required_arrays=("Open", "High", "Low", "Close", "Volume"),
        store_dir=tmp_path,
    )
    cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        store_dir=tmp_path,
    )

    frame = cache.fetch("ESH4", date(2024, 1, 1), date(2024, 1, 5))

    assert provider.calls == []
    assert list(frame.index) == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-01-05"),
    ]


def test_raw_leg_cache_empty_provider_response_is_persistently_covered(tmp_path) -> None:
    provider = _Provider()

    def empty_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        provider.calls.append((symbol, start, end))
        return pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"],
            index=pd.DatetimeIndex([]),
        )

    first_cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=empty_fetch,
        store_dir=tmp_path,
    )
    second_cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=empty_fetch,
        store_dir=tmp_path,
    )

    first = first_cache.fetch("GCK4", date(2024, 5, 1), date(2024, 5, 5))
    second = second_cache.fetch("GCK4", date(2024, 5, 1), date(2024, 5, 5))

    assert provider.calls == [("GCK4", date(2024, 5, 1), date(2024, 5, 5))]
    pd.testing.assert_frame_equal(
        first,
        pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"],
            index=pd.DatetimeIndex([]),
        ),
    )
    pd.testing.assert_frame_equal(first, second)


def test_raw_leg_cache_missing_required_array_raises_coverage_error(tmp_path) -> None:
    provider = _Provider()
    leg = RawFuturesLeg("GLBX.MDP3", "ESH4")
    merge_raw_futures_leg(
        leg,
        "1D",
        pd.DataFrame(
            {"Close": [1.0, 2.0]},
            index=pd.DatetimeIndex(["2024-01-01", "2024-01-02"]),
        ),
        store_dir=tmp_path,
    )
    cache = RawLegCache(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        arrays=("Close", "Volume"),
        store_dir=tmp_path,
    )

    with pytest.raises(StoreCoverageError, match="missing arrays \\['Volume'\\]"):
        cache.fetch("ESH4", date(2024, 1, 1), date(2024, 1, 2))

    assert provider.calls == []


def test_raw_leg_ports_bind_daily_fetch_and_probe_to_same_cache(tmp_path) -> None:
    provider = _Provider()
    ports = raw_leg_ports(
        dataset="GLBX.MDP3",
        timeframe="1D",
        fetch=provider,
        store_dir=tmp_path,
    )

    volume = ports.probe("ESH4", date(2024, 1, 1), date(2024, 1, 5))
    deliverable = ports.fetch("ESH4", date(2024, 1, 2), date(2024, 1, 4))

    assert provider.calls == [("ESH4", date(2024, 1, 1), date(2024, 1, 5))]
    assert volume.tolist() == [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]
    assert deliverable["Close"].tolist() == [277.0, 278.0, 279.0]

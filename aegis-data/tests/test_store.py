"""OS-global parquet store (aegis-data)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from aegis_runtime import ListedRef

from aegis_data.store import (
    FxPair,
    StoreCoverageError,
    cached_fetcher,
    data_dir,
    ListedAdjustmentPolicy,
    native_bars_path,
    read_fx_history,
    read_native_bars,
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

    frames = read_native_bars(
        (ref,),
        arrays=("close",),
        timeframe="1D",
        start="2024-03-28",
        end="2024-04-02",
        store_dir=tmp_path,
    )

    assert frames[ref]["close"].tolist() == [100.0, 101.0]


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
            store_dir=tmp_path,
        )

    assert "EUR/USD" in str(exc.value)
    assert "2024-01-03" in str(exc.value)

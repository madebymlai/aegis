"""OS-global parquet store (aegis-data)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from aegis_data.store import cached_fetcher, data_dir


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

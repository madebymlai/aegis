"""Contract-chain assembly + roll-date snapping (aegis-data).

The chain turns a futures root + date range into per-contract OHLCV plus the
roll dates, with adjacent contracts overlapping on the roll date.  The fetch is
injected, so assembly + snapping are tested without I/O.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from aegis_data.chain import fetch_contract_chain
from aegis_data.roll import DatedContract


def _es_2024(root: str, start: date, end: date) -> list[DatedContract]:
    """ES quarterly contracts (third-Friday expiries), as a definition source would list."""
    return [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
        DatedContract("ESZ4", date(2024, 12, 20)),
    ]


def _ohlcv(start: date, end: date, base: float) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    return pd.DataFrame(
        {"Open": close, "High": [c + 1 for c in close], "Low": [c - 1 for c in close],
         "Close": close, "Volume": [1000] * len(idx)},
        index=idx,
    )


def test_fetch_contract_chain_assembles_per_contract_bars_with_roll_overlap() -> None:
    fetched: list[str] = []

    def fake_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        fetched.append(symbol)
        base = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}[symbol]
        return _ohlcv(start, end, base)

    chain = fetch_contract_chain(
        "ES", date(2024, 1, 1), date(2024, 12, 31),
        list_contracts=_es_2024, fetch=fake_fetch, bar_cadence=timedelta(days=1),
    )

    assert chain.symbols == ("ESH4", "ESM4", "ESU4", "ESZ4")
    assert fetched == ["ESH4", "ESM4", "ESU4", "ESZ4"]
    assert len(chain.roll_dates) == 3
    assert len(chain.frames) == 4
    for i, roll in enumerate(chain.roll_dates):
        roll_ts = pd.Timestamp(roll)
        assert roll_ts in chain.frames[i].index
        assert roll_ts in chain.frames[i + 1].index


def test_chain_rolls_on_supplied_monthly_contracts() -> None:
    # Contracts are injected (from instrument definitions), so a monthly product builds a
    # monthly chain — no quarterly approximation.
    def list_contracts(root: str, start: date, end: date) -> list[DatedContract]:
        return [
            DatedContract("CLN6", date(2026, 6, 22)),
            DatedContract("CLQ6", date(2026, 7, 21)),
            DatedContract("CLU6", date(2026, 8, 20)),
        ]

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        return _ohlcv(start, end, {"CLN6": 50.0, "CLQ6": 60.0, "CLU6": 70.0}[symbol])

    chain = fetch_contract_chain(
        "CL",
        date(2026, 6, 1),
        date(2026, 9, 30),
        list_contracts=list_contracts,
        fetch=fetch,
        bar_cadence=timedelta(days=1),
    )

    assert chain.symbols == ("CLN6", "CLQ6", "CLU6")
    assert len(chain.roll_dates) == 2


def test_roll_dates_snap_back_to_the_latest_common_trading_day() -> None:
    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        idx = pd.bdate_range(start, end)
        idx = idx[idx != pd.Timestamp("2024-03-08")]  # scheduled roll on a non-trading day
        base = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}[symbol]
        close = [base + i for i in range(len(idx))]
        return pd.DataFrame(
            {"Open": close, "High": close, "Low": close, "Close": close, "Volume": [1] * len(idx)},
            index=idx,
        )

    chain = fetch_contract_chain(
        "ES", date(2024, 1, 1), date(2024, 12, 31),
        list_contracts=_es_2024, fetch=fetch, bar_cadence=timedelta(days=1),
    )

    assert chain.roll_dates[0] == pd.Timestamp("2024-03-07")
    assert pd.Timestamp("2024-03-07") in chain.frames[0].index
    assert pd.Timestamp("2024-03-07") in chain.frames[1].index

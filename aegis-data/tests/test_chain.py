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


def _gc_2024_with_serials(root: str, start: date, end: date) -> list[DatedContract]:
    """GC over summer 2024: the liquid even-month contracts plus the May/July serials,
    as a definition source lists them (no hardcoded cycle)."""
    return [
        DatedContract("GCK4", date(2024, 5, 28)),  # May serial
        DatedContract("GCM4", date(2024, 6, 26)),  # June liquid
        DatedContract("GCN4", date(2024, 7, 29)),  # July serial
        DatedContract("GCQ4", date(2024, 8, 28)),  # August liquid
    ]


def test_fetch_contract_chain_holds_only_the_liquid_cycle() -> None:
    # With a daily-volume probe, the chain rolls GCM4 -> GCQ4 and never through the
    # thin May/July serials; only the liquid legs are deliverable-fetched.
    liquid = {"GCM4", "GCQ4"}
    last_trade = {c.symbol: c.last_trade for c in _gc_2024_with_serials("GC", date(2024, 5, 1), date(2024, 8, 1))}
    fetched: list[str] = []

    def probe_volume(symbol: str, start: date, end: date) -> pd.Series:
        # A real provider returns no bars past a contract's last trade, so each leg's
        # volume is clamped to its own life: GCM4 leads through June, then GCQ4 leads.
        index = pd.bdate_range(start, min(end, last_trade[symbol]))
        level = 1000.0 if symbol in liquid else 50.0
        return pd.Series([level] * len(index), index=index, dtype="float64")

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        fetched.append(symbol)
        base = {"GCM4": 2000.0, "GCQ4": 2100.0}[symbol]
        return _ohlcv(start, end, base)

    chain = fetch_contract_chain(
        "GC", date(2024, 5, 1), date(2024, 8, 1),
        list_contracts=_gc_2024_with_serials, fetch=fetch,
        bar_cadence=timedelta(days=1), probe_volume=probe_volume,
    )

    assert chain.symbols == ("GCM4", "GCQ4")
    assert fetched == ["GCM4", "GCQ4"]
    assert len(chain.roll_dates) == 1
    roll = chain.roll_dates[0]
    assert roll in chain.frames[0].index
    assert roll in chain.frames[1].index


def test_liquidity_probe_windows_each_candidate_to_its_own_last_trade() -> None:
    """Regression (ICE symbology gap): the probe must fetch each candidate over a window
    ending at *its own* last trade, not the full chain window.

    The per-contract definitions snapshot is anchored at the fetch window's late edge, and
    a contract is only listed for a bounded horizon before expiry (ICE lists ~10 months
    out).  Probing every candidate over the full multi-year window made far-dated contracts
    unresolvable (Databento 422) because the window's edge fell before they were listed.
    Windowing each probe to the candidate's last trade keeps the definitions anchor inside
    the contract's listed life.
    """
    probed: dict[str, tuple[date, date]] = {}

    def probe_volume(symbol: str, start: date, end: date) -> pd.Series:
        probed[symbol] = (start, end)
        index = pd.bdate_range(start, end)
        return pd.Series([1000.0] * len(index), index=index, dtype="float64")

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        base = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}[symbol]
        return _ohlcv(start, end, base)

    fetch_contract_chain(
        "ES", date(2024, 1, 2), date(2024, 12, 31),
        list_contracts=_es_2024, fetch=fetch,
        bar_cadence=timedelta(days=1), probe_volume=probe_volume,
    )

    last_trade = {c.symbol: c.last_trade for c in _es_2024("ES", date(2024, 1, 2), date(2024, 12, 31))}
    # Each candidate is probed to its own last trade — never the full 2024-12-31 window edge.
    for symbol, (_probe_start, probe_end) in probed.items():
        assert probe_end == last_trade[symbol], f"{symbol} probed to {probe_end}, not its last trade"


def test_liquidity_probe_skips_a_candidate_expiring_before_the_window() -> None:
    """Regression (RB 2019): a candidate whose last trade falls *before* the window start —
    pulled in by the calendar's lookback anchor — must not be probed.  Its probe window would
    invert (``start`` > ``min(last_trade, end)``), and the leg cache rejects an end-on-or-before
    -start window, aborting the pull.  Such a contract expired before the window, can never be
    the Liquidity Leader, and is dropped from the Liquid Cycle.
    """

    def _with_expired_leg(root: str, start: date, end: date) -> list[DatedContract]:
        # An already-expired Dec-2023 leg listed just before the 2024 window opens.
        return [DatedContract("ESZ3", date(2023, 12, 15)), *_es_2024(root, start, end)]

    probed: list[str] = []

    def probe_volume(symbol: str, start: date, end: date) -> pd.Series:
        assert end >= start, f"{symbol} probed with inverted window {start}..{end}"
        probed.append(symbol)
        index = pd.bdate_range(start, end)
        return pd.Series([1000.0] * len(index), index=index, dtype="float64")

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        base = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}[symbol]
        return _ohlcv(start, end, base)

    chain = fetch_contract_chain(
        "ES", date(2024, 1, 2), date(2024, 12, 31),
        list_contracts=_with_expired_leg, fetch=fetch,
        bar_cadence=timedelta(days=1), probe_volume=probe_volume,
    )

    assert "ESZ3" not in probed  # the expired-before-window leg is never probed
    assert "ESZ3" not in chain.symbols


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

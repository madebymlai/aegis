"""Nautilus databento port fetcher (aegis-data).

The port path (definitions → bars → pandas) is verified with a fake async
client; the live call is covered by the env-gated smoke test.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from aegis_data.databento_port import (
    bars_to_ohlcv,
    databento_contract_calendar,
    databento_port_fetcher,
)


class _FakeDefStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def to_df(self) -> pd.DataFrame:
        return self._frame


class _FakeDatabento:
    """Stub Databento historical client replaying one ``frame`` and recording every query."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame
        self.timeseries = self
        self.queries: list[dict] = []

    def get_range(self, **kwargs) -> _FakeDefStore:
        self.queries.append(kwargs)
        return _FakeDefStore(self._frame)

    @property
    def kwargs(self) -> dict:
        return self.queries[-1] if self.queries else {}


class _SequencedDatabento:
    """Stub replaying a queue of frames, one per successive query (last frame repeats).

    Models a window that outruns the listed forward curve: the first snapshot lists only the
    near contracts, a later snapshot (taken at the coverage frontier) shows ones that list later.
    """

    def __init__(self, frames: list[pd.DataFrame]) -> None:
        self._frames = frames
        self.timeseries = self
        self.queries: list[dict] = []

    def get_range(self, **kwargs) -> _FakeDefStore:
        self.queries.append(kwargs)
        return _FakeDefStore(self._frames[min(len(self.queries) - 1, len(self._frames) - 1)])


def test_contract_calendar_lists_outright_futures_from_definitions() -> None:
    # A real definition frame mixes outright futures ("F") with spreads ("S") and repeats
    # a contract across days.  The calendar keeps only deduped outright futures and maps the
    # expiration timestamp to a last-trade date.
    frame = pd.DataFrame(
        {
            "raw_symbol": ["CLN6", "CLQ6", "CL-CLQ6", "CLN6"],
            "instrument_class": ["F", "F", "S", "F"],
            "expiration": pd.to_datetime(
                [
                    "2026-06-22 18:30:00+00:00",
                    "2026-07-21 18:30:00+00:00",
                    "2026-06-15 18:30:00+00:00",
                    "2026-06-22 18:30:00+00:00",
                ]
            ),
        }
    )
    client = _FakeDatabento(frame)

    contracts = databento_contract_calendar("GLBX.MDP3", client=client)(
        "CL", date(2026, 6, 1), date(2026, 7, 21)
    )

    assert [c.symbol for c in contracts] == ["CLN6", "CLQ6"]  # spread dropped, duplicate collapsed
    assert contracts[0].last_trade == date(2026, 6, 22)
    # Parent symbology drives the definition query.
    assert client.kwargs["symbols"] == ["CL.FUT"]
    assert client.kwargs["stype_in"] == "parent"


def test_contract_calendar_empty_definitions_is_empty() -> None:
    client = _FakeDatabento(pd.DataFrame())

    contracts = databento_contract_calendar("GLBX.MDP3", client=client)(
        "CL", date(2026, 6, 1), date(2026, 8, 1)
    )

    assert contracts == []


def test_contract_calendar_single_snapshot_covers_window() -> None:
    # A definition snapshot returns the whole forward curve CME lists (years out), so one
    # snapshot whose furthest expiry already reaches past the window end suffices — a single
    # bounded query, not a scan of every day in the panel.
    frame = pd.DataFrame(
        {
            "raw_symbol": ["CLN6", "CLQ6", "CLZ6"],
            "instrument_class": ["F", "F", "F"],
            "expiration": pd.to_datetime(
                [
                    "2026-06-22 18:30:00+00:00",
                    "2026-07-21 18:30:00+00:00",
                    "2026-12-21 18:30:00+00:00",  # furthest listed expiry — past the window end
                ]
            ),
        }
    )
    client = _FakeDatabento(frame)

    contracts = databento_contract_calendar("GLBX.MDP3", client=client)(
        "CL", date(2026, 6, 1), date(2026, 8, 1)
    )

    # One bounded 24h snapshot — not the 61-day panel — because the curve already covers the window.
    assert len(client.queries) == 1
    q = client.queries[0]
    assert (date.fromisoformat(q["end"]) - date.fromisoformat(q["start"])).days == 1
    # The snapshot enumerates the whole forward chain, including far-dated CLZ6, sorted by expiry.
    assert [c.symbol for c in contracts] == ["CLN6", "CLQ6", "CLZ6"]


def test_contract_calendar_resamples_when_window_outruns_listed_curve() -> None:
    # A window longer than the listing horizon outruns the curve listed at the start: the
    # first snapshot reaches only 2026-06-22, so the calendar resamples at the frontier, where
    # the deferred CLZ6 has since listed, and unions it in with no duplicate CLN6.
    near = pd.DataFrame(
        {
            "raw_symbol": ["CLN6"],
            "instrument_class": ["F"],
            "expiration": pd.to_datetime(["2026-06-22 18:30:00+00:00"]),
        }
    )
    far = pd.DataFrame(
        {
            "raw_symbol": ["CLN6", "CLZ6"],
            "instrument_class": ["F", "F"],
            "expiration": pd.to_datetime(
                ["2026-06-22 18:30:00+00:00", "2026-12-21 18:30:00+00:00"]
            ),
        }
    )
    client = _SequencedDatabento([near, far])

    contracts = databento_contract_calendar("GLBX.MDP3", client=client)(
        "CL", date(2026, 6, 1), date(2026, 9, 1)
    )

    # Two bounded 24h snapshots: the second is the resample at the coverage frontier.
    assert len(client.queries) == 2
    for q in client.queries:
        assert (date.fromisoformat(q["end"]) - date.fromisoformat(q["start"])).days == 1
    assert sorted(c.symbol for c in contracts) == ["CLN6", "CLZ6"]


def test_contract_calendar_snaps_a_weekend_anchor_to_a_weekday() -> None:
    # Definitions snapshot only Mon–Fri.  2024-06-01 is a Saturday, so the query must move to
    # the next weekday (Monday 2024-06-03) — otherwise a weekend anchor returns nothing.
    frame = pd.DataFrame(
        {
            "raw_symbol": ["CLZ6"],
            "instrument_class": ["F"],
            "expiration": pd.to_datetime(["2026-12-21 18:30:00+00:00"]),
        }
    )
    client = _FakeDatabento(frame)

    databento_contract_calendar("GLBX.MDP3", client=client)(
        "CL", date(2024, 6, 1), date(2024, 6, 20)
    )

    assert client.queries[0]["start"] == "2024-06-03"  # Saturday -> Monday
    assert date.fromisoformat(client.queries[0]["start"]).weekday() < 5


def test_contract_calendar_query_volume_is_coverage_bounded_not_window_proportional() -> None:
    # REGRESSION GUARD: the calendar once scanned the whole panel window, pulling a per-day
    # definition snapshot for every day.  Query volume must track the listed curve's coverage,
    # not the window length: a 10x-longer window the curve already covers fetches no more, and
    # no query ever spans more than a single 24h snapshot.
    frame = pd.DataFrame(
        {
            "raw_symbol": ["CLG26", "CLZ45"],
            "instrument_class": ["F", "F"],
            "expiration": pd.to_datetime(
                ["2026-02-20 18:30:00+00:00", "2045-12-19 18:30:00+00:00"]  # curve reaches 2045
            ),
        }
    )
    short, long = _FakeDatabento(frame), _FakeDatabento(frame)
    databento_contract_calendar("GLBX.MDP3", client=short)("CL", date(2026, 1, 1), date(2026, 2, 1))
    databento_contract_calendar("GLBX.MDP3", client=long)("CL", date(2026, 1, 1), date(2036, 1, 1))

    assert len(short.queries) == len(long.queries) == 1  # window length does not add queries
    for q in (*short.queries, *long.queries):
        assert (date.fromisoformat(q["end"]) - date.fromisoformat(q["start"])).days == 1


class _Px:
    def __init__(self, value: float) -> None:
        self._value = value

    def as_double(self) -> float:
        return self._value


class _Bar:
    def __init__(self, ts: int, o: float, h: float, low: float, c: float, v: float) -> None:
        self.ts_event = ts
        self.open, self.high, self.low, self.close, self.volume = (
            _Px(o), _Px(h), _Px(low), _Px(c), _Px(v),
        )


class _FakeClient:
    def __init__(self, bars: list[_Bar]) -> None:
        self._bars = bars
        self.calls: list[str] = []
        self.instr_window: tuple[int, int] | None = None
        self.bars_window: tuple[int, int] | None = None

    async def get_range_instruments(self, dataset, ids, start_ns, end_ns, *a, **k) -> list:
        self.calls.append("instruments")
        self.instr_window = (start_ns, end_ns)
        return []

    async def get_range_bars(self, dataset, ids, agg, start_ns, end_ns, *a, **k) -> list[_Bar]:
        self.calls.append("bars")
        self.bars_window = (start_ns, end_ns)
        return self._bars


def test_bars_to_ohlcv_normalizes_pyo3_bars() -> None:
    bars = [_Bar(pd.Timestamp("2024-09-13").value, 5665.75, 5702.25, 5659.75, 5687.5, 291354)]

    df = bars_to_ohlcv(bars)

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.tz is None
    assert df.loc[pd.Timestamp("2024-09-13"), "Close"] == 5687.5
    assert df.loc[pd.Timestamp("2024-09-13"), "Volume"] == 291354.0


def test_fetcher_loads_definitions_before_bars() -> None:
    client = _FakeClient([_Bar(pd.Timestamp("2024-09-13").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("GLBX.MDP3", client=client)

    df = fetch("ESZ4", date(2024, 9, 13), date(2024, 9, 13))

    # Definitions must be fetched before bars (so the port resolves precision).
    assert client.calls == ["instruments", "bars"]
    assert df.loc[pd.Timestamp("2024-09-13"), "Close"] == 1.5


def test_fetcher_loads_definitions_over_a_single_weekday_not_the_bars_window() -> None:
    # Price precision is static, so loading definitions over the whole bars window pulls a
    # per-day snapshot for every day and dominates the fetch.  The definition load is one day,
    # snapped onto a weekday (a weekend anchor returns no snapshot); the bars keep the full span.
    client = _FakeClient([_Bar(pd.Timestamp("2024-09-13").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("GLBX.MDP3", client=client)

    fetch("ESU4", date(2024, 6, 1), date(2024, 9, 25))  # 2024-06-01 is a Saturday

    one_day = pd.Timedelta(days=1).value
    instr_start, instr_end = client.instr_window
    bars_start, bars_end = client.bars_window
    assert instr_end - instr_start == one_day              # definitions: a single day
    assert instr_start == pd.Timestamp("2024-06-03").value  # Saturday start snapped to Monday
    assert bars_start == pd.Timestamp("2024-06-01").value   # bars keep the true window start
    assert bars_end - bars_start > one_day                  # bars: the full multi-month span


def test_fetcher_definition_load_is_constant_regardless_of_bars_window() -> None:
    # REGRESSION GUARD: the port once loaded definitions over the whole bars window, pulling a
    # per-day snapshot for every day (99s cold for a multi-month contract).  Precision is static,
    # so the definition load stays one day no matter how long the bars span — only bars scale.
    bar = [_Bar(pd.Timestamp("2024-06-03").value, 1.0, 2.0, 0.5, 1.5, 100)]
    short, long = _FakeClient(list(bar)), _FakeClient(list(bar))
    databento_port_fetcher("GLBX.MDP3", client=short)("ESU4", date(2024, 6, 3), date(2024, 6, 10))
    databento_port_fetcher("GLBX.MDP3", client=long)("ESU4", date(2024, 6, 3), date(2034, 6, 10))

    one_day = pd.Timedelta(days=1).value
    short_defs = short.instr_window[1] - short.instr_window[0]
    long_defs = long.instr_window[1] - long.instr_window[0]
    assert short_defs == long_defs == one_day  # definition volume does not grow with the window
    # ...while the bars window does scale, proving the contrast is real, not both pinned to one day.
    assert (long.bars_window[1] - long.bars_window[0]) > (short.bars_window[1] - short.bars_window[0])

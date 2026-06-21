"""Nautilus databento port fetcher (aegis-data).

The port path (definitions → bars → pandas) is verified with a fake async
client; the live call is covered by the env-gated smoke test.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

import pytest

from aegis_data.databento_port import (
    bars_to_ohlcv,
    databento_contract_calendar,
    databento_port_fetcher,
    retrying_fetcher,
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


def test_contract_calendar_drops_ice_trade_at_settlement_variant_keeping_base_outright() -> None:
    # REGRESSION (aegis-rd-min): ICE lists each delivery month under its base outright
    # (switch character "!" — "no additional data", ICE Instrument Naming Convention §1.8.1)
    # AND auxiliary markets that share the same expiration and that Databento also classes
    # "F" — notably Trade-at-Settlement ("_Z", §1.8.5.4).  Keying by raw_symbol admitted both,
    # so one expiry produced two DatedContracts and chain assembly aborted at the seam.  The
    # calendar must collapse each expiry to its single "!" base outright.
    frame = pd.DataFrame(
        {
            "raw_symbol": ["DX  FMH0019!", "DX  FMH0019_Z", "DX  FMM0019!", "DX  FMM0019_Z"],
            "instrument_class": ["F", "F", "F", "F"],  # TAS is classed "F", so the "F" filter keeps it
            "expiration": pd.to_datetime(
                [
                    "2019-03-18 21:00:00+00:00",
                    "2019-03-18 21:00:00+00:00",  # _Z shares the base future's expiration
                    "2019-06-17 21:00:00+00:00",
                    "2019-06-17 21:00:00+00:00",
                ]
            ),
        }
    )
    client = _FakeDatabento(frame)

    contracts = databento_contract_calendar("IFUS.IMPACT", client=client)(
        "DX", date(2019, 1, 1), date(2019, 6, 1)
    )

    # One contract per expiry — the "!" base outright; the "_Z" TAS variant is dropped.
    assert [c.symbol for c in contracts] == ["DX  FMH0019!", "DX  FMM0019!"]
    assert [c.last_trade for c in contracts] == [date(2019, 3, 18), date(2019, 6, 17)]


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


def _ohlcv(symbol: str, start: date, end: date) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [100.0]},
        index=pd.DatetimeIndex([pd.Timestamp(start)]),
    )


def test_retrying_fetcher_retries_a_transient_provider_error_then_succeeds() -> None:
    # A single Databento 504 gateway timeout must not abort a long sequential pull.
    calls: list[int] = []
    slept: list[float] = []

    def flaky(symbol: str, start: date, end: date) -> pd.DataFrame:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("Failed to get range: API error: 504 Gateway Timeout")
        return _ohlcv(symbol, start, end)

    fetch = retrying_fetcher(flaky, attempts=4, sleep=slept.append)
    out = fetch("6JU4", date(2024, 6, 3), date(2024, 9, 20))

    assert len(calls) == 3  # two failures, third succeeds
    assert len(slept) == 2  # backed off between attempts
    assert out["Close"].iloc[0] == 1.5


def test_retrying_fetcher_does_not_retry_a_non_transient_error() -> None:
    # A bad symbol / auth failure is permanent — fail fast, don't waste the retry budget.
    calls: list[int] = []

    def bad(symbol: str, start: date, end: date) -> pd.DataFrame:
        calls.append(1)
        raise ValueError("symbology resolution failed: unknown symbol")

    fetch = retrying_fetcher(bad, attempts=4, sleep=lambda _s: None)
    with pytest.raises(ValueError, match="unknown symbol"):
        fetch("NOPE", date(2024, 6, 3), date(2024, 9, 20))

    assert len(calls) == 1  # no retries


def test_retrying_fetcher_gives_up_after_max_attempts() -> None:
    calls: list[int] = []

    def always_504(symbol: str, start: date, end: date) -> pd.DataFrame:
        calls.append(1)
        raise RuntimeError("504 Gateway Time-out")

    fetch = retrying_fetcher(always_504, attempts=3, sleep=lambda _s: None)
    with pytest.raises(RuntimeError, match="504"):
        fetch("6JU4", date(2024, 6, 3), date(2024, 9, 20))

    assert len(calls) == 3  # exactly the attempt budget, then surfaces the error


def test_port_fetcher_survives_a_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Wiring: the production port fetcher applies the retry, so one flaky call is absorbed.
    monkeypatch.setattr("aegis_data.databento_port.time.sleep", lambda _s: None)

    class _FlakyClient(_FakeClient):
        def __init__(self, bars: list[_Bar]) -> None:
            super().__init__(bars)
            self._fails = 1

        async def get_range_instruments(self, *a, **k) -> list:
            if self._fails > 0:
                self._fails -= 1
                raise RuntimeError("API error: 504 Gateway Timeout")
            return await super().get_range_instruments(*a, **k)

    client = _FlakyClient([_Bar(pd.Timestamp("2024-09-13").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("GLBX.MDP3", client=client)

    df = fetch("ESZ4", date(2024, 9, 13), date(2024, 9, 13))

    assert df.loc[pd.Timestamp("2024-09-13"), "Close"] == 1.5


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


def test_fetcher_anchors_definitions_as_a_bounded_lookback_at_the_window_late_edge() -> None:
    # Price precision is static, so definitions load over a short bounded window, not the whole
    # bars span.  The window is anchored at the bars' LATE edge — inside the contract's listed
    # life (a contract is only listed a bounded horizon before expiry) — with a lookback rather
    # than a single day, so an expiry-day delisting still leaves an active definition to resolve.
    client = _FakeClient([_Bar(pd.Timestamp("2024-09-13").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("GLBX.MDP3", client=client)

    fetch("ESU4", date(2024, 6, 3), date(2024, 9, 29))

    fifteen_days = pd.Timedelta(days=15).value  # 14-day lookback + the end-exclusive guard day
    instr_start, instr_end = client.instr_window
    bars_start, bars_end = client.bars_window
    assert instr_end - instr_start == fifteen_days           # definitions: a bounded lookback
    assert instr_end == pd.Timestamp("2024-09-30").value     # window ends just past the late edge
    assert instr_start == pd.Timestamp("2024-09-15").value   # ...looking back 14 days from the edge
    assert bars_start == pd.Timestamp("2024-06-03").value    # bars keep the true window start
    assert bars_end - bars_start > fifteen_days              # bars: the full multi-month span


def test_fetcher_resolves_a_contract_listed_only_late_in_the_window() -> None:
    """Regression (ICE symbology gap): a contract listed only near expiry must resolve when
    fetched over a window that opens before it was listed.

    ICE lists a contract a bounded horizon before expiry, so a definitions snapshot taken at
    the window START — years before, as the liquidity probe spans the whole panel — cannot
    resolve it (Databento 422 symbology_invalid_request).  Anchoring the snapshot at the
    window's late edge, inside the contract's listed life, resolves it.
    """
    listed_from = pd.Timestamp("2024-06-01").value

    class _LateListed(_FakeClient):
        async def get_range_instruments(self, dataset, ids, start_ns, end_ns, *a, **k) -> list:
            if end_ns <= listed_from:  # a snapshot taken before the contract was listed
                raise ValueError(
                    "Failed to get range: API error: 422 Unprocessable Entity None of the "
                    "symbols could be resolved (case: symbology_invalid_request)"
                )
            return await super().get_range_instruments(dataset, ids, start_ns, end_ns, *a, **k)

    client = _LateListed([_Bar(pd.Timestamp("2024-09-13").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("IFUS.IMPACT", client=client)

    # Probe-style: the window opens in 2019 (before listing) but ends at the contract's last trade.
    df = fetch("DX  FMU0024", date(2019, 1, 1), date(2024, 9, 16))

    assert df.loc[pd.Timestamp("2024-09-13"), "Close"] == 1.5


def test_fetcher_resolves_a_contract_delisted_on_its_last_trade_day() -> None:
    """Regression (ICE defs-anchor edge case): a contract whose definition is dropped from the
    active set on its last-trade day — because it stopped trading earlier (last bar < last
    trade, e.g. DX FMH0024: last bar 2024-03-15, expiry Monday 2024-03-18) — must still resolve
    price precision when the window ends at that last-trade day.

    A single-day definitions snapshot anchored at exactly the late edge lands on the delisted
    day and cannot resolve precision (Databento ValueError: "Could not resolve price_precision").
    A short lookback window ending at the late edge spans days where the definition is still
    active, so precision resolves; it stays inside the listed life (no 422) and bounded (fast).
    """
    delisted_from = pd.Timestamp("2024-03-18").value  # the definition is gone on/after this day

    class _DelistedAtExpiry(_FakeClient):
        def __init__(self, bars: list[_Bar]) -> None:
            super().__init__(bars)
            self._precision_resolved = False

        async def get_range_instruments(self, dataset, ids, start_ns, end_ns, *a, **k) -> list:
            await super().get_range_instruments(dataset, ids, start_ns, end_ns, *a, **k)
            if start_ns < delisted_from:  # the window reaches a day the definition is still active
                self._precision_resolved = True
            return []

        async def get_range_bars(self, dataset, ids, agg, start_ns, end_ns, *a, **k) -> list[_Bar]:
            if not self._precision_resolved:  # the port raises this when no definition was loaded
                raise ValueError(
                    "Could not resolve `price_precision` for DX  FMH0024!.IFUS: pass "
                    "`price_precision` explicitly, call `set_price_precision`, or fetch the "
                    "instrument definitions first via `get_range_instruments`"
                )
            return await super().get_range_bars(dataset, ids, agg, start_ns, end_ns, *a, **k)

    client = _DelistedAtExpiry([_Bar(pd.Timestamp("2024-03-15").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("IFUS.IMPACT", client=client)

    # Probe-style window ending at the contract's last-trade day (a weekday), the delisted day.
    df = fetch("DX  FMH0024!", date(2019, 1, 1), date(2024, 3, 18))

    assert df.loc[pd.Timestamp("2024-03-15"), "Close"] == 1.5


def test_fetcher_definition_load_is_constant_regardless_of_bars_window() -> None:
    # REGRESSION GUARD: the port once loaded definitions over the whole bars window, pulling a
    # per-day snapshot for every day (99s cold for a multi-month contract).  Precision is static,
    # so the definition load stays a bounded lookback no matter how long the bars span — only
    # the bars scale.
    bar = [_Bar(pd.Timestamp("2024-06-03").value, 1.0, 2.0, 0.5, 1.5, 100)]
    short, long = _FakeClient(list(bar)), _FakeClient(list(bar))
    databento_port_fetcher("GLBX.MDP3", client=short)("ESU4", date(2024, 6, 3), date(2024, 6, 10))
    databento_port_fetcher("GLBX.MDP3", client=long)("ESU4", date(2024, 6, 3), date(2034, 6, 10))

    fifteen_days = pd.Timedelta(days=15).value  # 14-day lookback + the end-exclusive guard day
    short_defs = short.instr_window[1] - short.instr_window[0]
    long_defs = long.instr_window[1] - long.instr_window[0]
    assert short_defs == long_defs == fifteen_days  # definition volume does not grow with the window
    # ...while the bars window does scale, proving the contrast is real, not both pinned to one day.
    assert (long.bars_window[1] - long.bars_window[0]) > (short.bars_window[1] - short.bars_window[0])

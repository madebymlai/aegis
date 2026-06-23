"""The continuous feed — a RebalanceStrategy-owned deep module (r8b.9 Slice B, Model 2).

The feed owns the back-adjusted continuous series for one bare root.  It re-materializes the
series via aegis-data's request path (``continuous_ohlcv_frames`` — its own ephemeral engine +
Cache, never the live node cache), exposes the current front leg for execution routing, appends
today's front bar verbatim at offset 0, and re-materializes (re-based) across a roll.  Because
live literally runs the research materializer, ``live@T ≡ research over [start, T]`` by
construction.

These goldens use a synthetic two-leg ES catalog (ESH4 -> ESM4 on a liquidity migration),
mirroring aegis-data's ``test_continuous_catalog`` fixture, so the feed's output is pinned
against the same request-path oracle research uses.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.continuous_catalog import continuous_ohlcv_frames

_UTC = timezone.utc
_CLOSE = time(21, 0)  # bar stamp, strictly after the midnight roll boundary
_PRECISION = 2
_CROSSOVER = pd.Timestamp("2024-03-01")  # liquidity migrates ESH4 -> ESM4 here
_START, _END = "2024-01-15", "2024-05-31"
_ES_XCME = InstrumentId.from_str("ES.XCME")


def _future(instrument_id: str, expiry: str, *, underlying: str = "ES") -> FuturesContract:
    iid = InstrumentId.from_str(instrument_id)
    return FuturesContract(
        instrument_id=iid,
        raw_symbol=iid.symbol,
        asset_class=AssetClass.INDEX,
        exchange=iid.venue.value,
        currency=USD,
        price_precision=_PRECISION,
        price_increment=Price(10**-_PRECISION, _PRECISION),
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        underlying=underlying,
        activation_ns=0,
        expiration_ns=pd.Timestamp(expiry, tz="UTC").value,
        ts_event=0,
        ts_init=0,
    )


def _frame(start: str, end: str, base: float, *, leads_early: bool) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    volume = [(1000.0 if (day < _CROSSOVER) == leads_early else 100.0) for day in idx]
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def _bars(instrument_id: InstrumentId, frame: pd.DataFrame, stamp: time = _CLOSE) -> list[Bar]:
    bar_type = raw_bar_type(instrument_id, "1D")
    bars: list[Bar] = []
    for day, row in frame.iterrows():
        ts = int(datetime.combine(day.date(), stamp, _UTC).timestamp() * 1e9)
        bars.append(
            Bar(
                bar_type,
                Price.from_str(str(row["Open"])),
                Price.from_str(str(row["High"])),
                Price.from_str(str(row["Low"])),
                Price.from_str(str(row["Close"])),
                Quantity.from_int(int(row["Volume"])),
                ts,
                ts,
            )
        )
    return bars


class _FakeCatalog:
    def __init__(self, instruments: list[FuturesContract], bars: dict[str, list[Bar]]) -> None:
        self._instruments = instruments
        self._bars = bars

    def instruments(
        self,
        instrument_type: type | None = None,
        instrument_ids: list[str] | None = None,
        **_kwargs: object,
    ) -> list[FuturesContract]:
        out = self._instruments
        if instrument_type is not None:
            out = [i for i in out if isinstance(i, instrument_type)]
        if instrument_ids is not None:
            wanted = set(instrument_ids)
            out = [i for i in out if i.id.value in wanted]
        return out

    def query(
        self,
        data_cls: type,  # noqa: ARG002
        identifiers: list[str] | None = None,
        start: object = None,
        end: object = None,
        **_kwargs: object,
    ) -> list[Bar]:
        lo, hi = pd.Timestamp(start).value, pd.Timestamp(end).value
        return [
            bar
            for ident in (identifiers or [])
            for bar in self._bars.get(ident, [])
            if lo <= bar.ts_event <= hi
        ]


class _FakePort:
    def __init__(self, catalog: _FakeCatalog, frames: dict[InstrumentId, pd.DataFrame]) -> None:
        self.catalog = catalog
        self._frames = frames

    def load_raw_bars(self, request: object) -> dict[InstrumentId, pd.DataFrame]:
        start, end = pd.Timestamp(request.start), pd.Timestamp(request.end)  # type: ignore[attr-defined]
        return {
            iid: self._frames[iid].loc[
                (self._frames[iid].index >= start) & (self._frames[iid].index <= end)
            ]
            for iid in request.instrument_ids  # type: ignore[attr-defined]
        }

    def read_native_bars(self, request: object) -> dict[InstrumentId, list[Bar]]:
        return {
            iid: self.catalog.query(
                Bar,
                identifiers=[str(raw_bar_type(iid, request.timeframe))],  # type: ignore[attr-defined]
                start=request.start,  # type: ignore[attr-defined]
                end=request.end,  # type: ignore[attr-defined]
            )
            for iid in request.instrument_ids  # type: ignore[attr-defined]
        }


def _es_port(stamp: time = _CLOSE) -> tuple[_FakePort, dict[InstrumentId, list[Bar]]]:
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    frames = {
        esh4: _frame(_START, "2024-03-15", 100.0, leads_early=True),
        esm4: _frame(_START, "2024-04-30", 200.0, leads_early=False),
    }
    native = {iid: _bars(iid, frame, stamp) for iid, frame in frames.items()}
    catalog = _FakeCatalog(
        instruments=[_future("ESH4.XCME", "2024-03-15"), _future("ESM4.XCME", "2024-06-21")],
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
    )
    return _FakePort(catalog, frames), native


def _lead_frame(start: str, end: str, base: float, lead_lo: str, lead_hi: str) -> pd.DataFrame:
    """A leg frame whose volume dominates only inside ``[lead_lo, lead_hi]`` (its liquidity-lead
    window), so a chain of legs hands the lead off in expiry order."""
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    lo, hi = pd.Timestamp(lead_lo), pd.Timestamp(lead_hi)
    volume = [1000.0 if lo <= day <= hi else 50.0 for day in idx]
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def _es_port_two_rolls() -> tuple[_FakePort, dict[InstrumentId, list[Bar]]]:
    """A three-leg ES chain (ESH4 -> ESM4 -> ESU4) with two liquidity handoffs, so a roll can be
    exercised from a NON-empty pre-roll series (the realistic mid-run case)."""
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    esu4 = InstrumentId.from_str("ESU4.XCME")
    # Each leg loses the lead ~2 weeks before it expires (mirroring the proven single-seam
    # fixture: ESH4 crosses over 2024-03-01, expires 2024-03-15), so the volume-causal front
    # and the chain's expiry-aware roll agree on both seams.
    frames = {
        esh4: _lead_frame(_START, "2024-03-15", 100.0, _START, "2024-02-29"),
        esm4: _lead_frame(_START, "2024-06-21", 200.0, "2024-03-01", "2024-06-06"),
        esu4: _lead_frame("2024-03-01", "2024-09-19", 300.0, "2024-06-07", "2024-09-19"),
    }
    native = {iid: _bars(iid, frame) for iid, frame in frames.items()}
    catalog = _FakeCatalog(
        instruments=[
            _future("ESH4.XCME", "2024-03-15"),
            _future("ESM4.XCME", "2024-06-21"),
            _future("ESU4.XCME", "2024-09-20"),
        ],
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
    )
    return _FakePort(catalog, frames), native


def test_materializing_never_writes_the_continuous_series_into_the_live_cache() -> None:
    """B0 (isolation, the safety the feed relies on): the feed re-materializes on aegis-data's
    own ephemeral engine + cache, so a live node cache holding raw legs is untouched — the
    continuous target never lands there, and the raw legs survive (Model 2)."""
    from aegis_data.bar_type import continuous_bar_type
    from nautilus_trader.cache.cache import Cache

    from aegis_trader.data.continuous_feed import ContinuousFeed

    port, _native = _es_port()
    live_cache = Cache()
    esh4 = InstrumentId.from_str("ESH4.XCME")
    live_cache.add_instrument(_future("ESH4.XCME", "2024-03-15"))
    leg_bar = _bars(esh4, _frame(_START, "2024-01-20", 100.0, leads_early=True))[0]
    live_cache.add_bar(leg_bar)

    feed = ContinuousFeed(port, "ES", start=_START, timeframe="1D")
    feed.materialize(end=_END)

    assert live_cache.bars(continuous_bar_type(_ES_XCME, "1D")) == []
    assert live_cache.bar_count(raw_bar_type(esh4, "1D")) == 1


def test_feed_series_matches_the_request_oracle_byte_exact() -> None:
    """B1: the feed's series is the request-path materialization research uses, byte-for-byte,
    keyed by the synthetic continuous-root id."""
    from aegis_trader.data.continuous_feed import ContinuousFeed

    port, _native = _es_port()
    feed = ContinuousFeed(port, "ES", start=_START, timeframe="1D")
    feed.materialize(end=_END)

    oracle = continuous_ohlcv_frames(port, ["ES"], start=_START, end=_END, timeframe="1D")[_ES_XCME]

    assert feed.continuous_id == _ES_XCME
    pd.testing.assert_frame_equal(feed.series(), oracle)


def test_feed_front_contract_follows_the_causal_liquid_cycle() -> None:
    """B2: the front leg the feed exposes for execution is the causal liquid front (the latest
    leg that has led by ``end``).  Before the liquidity migration the near leg is front; after,
    the next leg.  At the window end the causal front coincides with the acausal one."""
    from aegis_trader.data.continuous_feed import ContinuousFeed

    port, _native = _es_port()
    feed = ContinuousFeed(port, "ES", start=_START, timeframe="1D")

    feed.materialize(end="2024-02-15")  # before ESH4 -> ESM4 liquidity migration
    assert feed.front_contract() == InstrumentId.from_str("ESH4.XCME")

    feed.materialize(end=_END)  # after the migration
    assert feed.front_contract() == InstrumentId.from_str("ESM4.XCME")


@pytest.mark.parametrize(
    ("stamp", "materialize_end", "append_day"),
    [
        # A close-of-day (00:00 UTC, as real IBKR daily bars are) front bar appends verbatim;
        # an intraday (21:00, the aegis-data golden convention) one rolls up to the next bucket.
        # The append must reproduce the engine's row byte-for-byte under BOTH stamps.
        (time(0, 0), "2024-04-29", date(2024, 4, 30)),
        (time(21, 0), "2024-04-30", date(2024, 4, 29)),
    ],
)
def test_offset_zero_append_reproduces_research_and_is_stamp_robust(
    stamp: time, materialize_end: str, append_day: date
) -> None:
    """B3: the live feed materializes the history (research minus its final still-forming bucket —
    the very row the bounded request omits), then appends today's front-leg bar verbatim (front
    offset 0 ⇒ today's continuous value IS the raw front close), recovering research-as-of-today
    byte-for-byte without waiting on IBKR historical — proven stamp-robust over 00:00 and 21:00."""
    from aegis_trader.data.continuous_feed import ContinuousFeed

    port, native = _es_port(stamp)
    esm4 = InstrumentId.from_str("ESM4.XCME")
    live_front_bar = next(
        b for b in native[esm4] if pd.Timestamp(b.ts_event, tz="UTC").date() == append_day
    )
    research = continuous_ohlcv_frames(
        port, ["ES"], start=_START, end="2024-05-10", timeframe="1D"
    )[_ES_XCME]

    feed = ContinuousFeed(port, "ES", start=_START, timeframe="1D")
    feed.materialize(end=materialize_end)
    pd.testing.assert_frame_equal(feed.series(), research.iloc[:-1])  # history through yesterday

    feed.on_bar(live_front_bar)  # append today's front bar verbatim at offset 0

    pd.testing.assert_frame_equal(feed.series(), research)  # == research-as-of-today, gap/dupe-free


def test_last_roll_spread_is_the_uniform_additive_rebase_at_a_roll() -> None:
    """D2: across a roll the whole series re-bases by one uniform additive spread Δ (BACKWARD_SPREAD
    shifts every earlier segment by the same post−pre gap).  The feed exposes that Δ as a query so
    the strategy can re-base the SleeveLedger's stored closes in lock-step (Slice L), keeping the
    allocator input basis-consistent across the roll.  Before any roll the spread is 0.0."""
    from aegis_trader.data.continuous_feed import ContinuousFeed

    port, native = _es_port_two_rolls()
    esu4 = InstrumentId.from_str("ESU4.XCME")

    feed = ContinuousFeed(port, "ES", start=_START, timeframe="1D")
    feed.materialize(end="2024-06-10")  # mid-run: front is ESM4, series already non-empty
    assert feed.last_roll_spread() == 0.0
    assert not feed.series().empty
    assert feed.front_contract() == InstrumentId.from_str("ESM4.XCME")

    pre = feed.series().copy()
    roll_bar = next(
        b for b in native[esu4] if pd.Timestamp(b.ts_event, tz="UTC").date() == date(2024, 6, 14)
    )
    feed.on_bar(roll_bar)  # second roll (ESM4 → ESU4) → re-base the whole series at the new front
    post = feed.series()
    assert feed.front_contract() == esu4

    common = pre.index.intersection(post.index)
    spread = feed.last_roll_spread()
    assert spread != 0.0
    # Δ is exactly the uniform shift carrying every pre-roll close from the old basis to the new.
    pd.testing.assert_series_equal(
        post.loc[common, "Close"], pre.loc[common, "Close"] + spread, check_names=False
    )


def test_roll_rematerializes_rebased_and_advances_the_front() -> None:
    """B4: when the causal liquid front advances (a roll), the feed re-materializes the whole
    series re-based at the new front and advances ``front_contract`` — live ≡ research across the
    roll, gap- and dupe-free."""
    from aegis_trader.data.continuous_feed import ContinuousFeed

    port, native = _es_port()
    esm4 = InstrumentId.from_str("ESM4.XCME")

    feed = ContinuousFeed(port, "ES", start=_START, timeframe="1D")
    feed.materialize(end="2024-02-15")  # pre-roll: front is the near leg
    assert feed.front_contract() == InstrumentId.from_str("ESH4.XCME")

    # the next leg has taken the liquidity lead; one of its bars arrives on the node
    roll_bar = next(
        b for b in native[esm4] if pd.Timestamp(b.ts_event, tz="UTC").date() == date(2024, 3, 20)
    )
    feed.on_bar(roll_bar)

    assert feed.front_contract() == esm4
    research = continuous_ohlcv_frames(
        port, ["ES"], start=_START, end="2024-03-20", timeframe="1D"
    )[_ES_XCME]
    pd.testing.assert_frame_equal(feed.series(), research)
    assert feed.series().index.is_monotonic_increasing
    assert not feed.series().index.has_duplicates

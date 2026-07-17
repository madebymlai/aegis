"""Adjustment golden parity: request- and subscribe-path continuous series are byte-exact.

Path A's gate (AC4): both the in-process ``request_bars`` (research) and the live
``subscribe_bars`` roll state machine, driven by the *same* roll-transition table the
producer builds, must reproduce — byte-for-byte — the continuous series of the independent
Decimal oracle, for BOTH shipped backward modes (parametrized).  Spread is integer-exact and
ratio is exact at this trading precision, so this is an exact ``==`` over the OHLC raw ints
(no tolerance) ⇒ live ≡ research.

The engine stamps each composite bar at its bucket close and drops the final
still-forming bucket, so the *request* series is the head of the oracle's; the live
*subscribe* series additionally emits that final bucket (it is exactly one bar longer).
Parity is asserted index-aligned over the overlap (prototype ``NOTES.md`` V1/V2/V4/V5).
"""

from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass, ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.chain import ContractChain
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.continuous_future import (
    DEFAULT_ADJUSTMENT_MODE,
    ContinuousFuture,
    continuous_future,
)
from aegis_data.continuous_materialize import materialize_continuous_bars
from aegis_data.testing import FakeCatalog, bars as production_bars
from tests.support.continuous_oracle import AdjustedBar, backward_series
from tests.support.continuous_subscribe import (
    materialize_continuous_bars_via_subscription,
)

_UTC = timezone.utc
_CLOSE = time(21, 0)  # intraday bar stamp, strictly after the midnight roll boundary
_PRECISION = 2
# Both shipped backward modes — the series must be byte-exact with the independent oracle for each.
_MODES = (
    ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    ContinuousFutureAdjustmentType.BACKWARD_RATIO,
)


def _frame(dates: list[str], close: list[float]) -> pd.DataFrame:
    return _frame_with_volume(dates, close, [100] * len(close))


def _frame_with_volume(
    dates: list[str], close: list[float], volume: list[int]
) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
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


def _future(instrument_id: InstrumentId, expiry: str | None = None) -> FuturesContract:
    increment = Price(10**-_PRECISION, _PRECISION)
    return FuturesContract(
        instrument_id=instrument_id,
        raw_symbol=instrument_id.symbol,
        asset_class=AssetClass.INDEX,
        exchange=instrument_id.venue.value,
        currency=USD,
        price_precision=_PRECISION,
        price_increment=increment,
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        underlying="ES",
        activation_ns=0,
        expiration_ns=0 if expiry is None else pd.Timestamp(expiry, tz="UTC").value,
        ts_event=0,
        ts_init=0,
    )


def _bars(
    instrument_id: InstrumentId, frame: pd.DataFrame, *, at: time = _CLOSE
) -> list[Bar]:
    bar_type = raw_bar_type(instrument_id, "1D")
    bars: list[Bar] = []
    for day, row in frame.iterrows():
        ts = int(datetime.combine(day.date(), at, _UTC).timestamp() * 1e9)
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


def _raws(bars: list[Bar]) -> list[tuple[int, int, int, int]]:
    return [(b.open.raw, b.high.raw, b.low.raw, b.close.raw) for b in bars]


def _oracle_raws(oracle: list[AdjustedBar]) -> list[tuple[int, int, int, int]]:
    return [(o.open_raw, o.high_raw, o.low_raw, o.close_raw) for o in oracle]


def _golden_model_port() -> CatalogBackedDataPort:
    esh4 = InstrumentId(Symbol("ESH4"), Venue("XCME"))
    esm4 = InstrumentId(Symbol("ESM4"), Venue("XCME"))
    pre = _frame_with_volume(
        ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"],
        [100.0, 101.0, 102.0, 103.0, 104.0],
        [1000, 1000, 1000, 100, 100],
    )
    post = _frame_with_volume(
        ["2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11", "2024-03-12"],
        [120.0, 121.0, 122.0, 123.0, 124.0],
        [100, 1000, 1000, 1000, 1000],
    )
    native = {esh4: production_bars(esh4, pre), esm4: production_bars(esm4, post)}
    catalog = FakeCatalog(
        [_future(esh4, "2024-03-15"), _future(esm4, "2024-06-21")],
        {
            str(raw_bar_type(instrument_id, "1D")): bars
            for instrument_id, bars in native.items()
        },
    )
    return CatalogBackedDataPort(catalog)


def _expected_model_ratio_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [116.7, 117.9, 119.1, 120.2, 121.5, 122.5],
            "High": [118.5, 119.7, 120.8, 122.0, 123.0, 124.0],
            "Low": [116.1, 117.3, 118.5, 119.7, 121.0, 122.0],
            "Close": [117.3, 118.5, 119.7, 120.8, 122.0, 123.0],
            "Volume": [1000.0, 1000.0, 1000.0, 100.0, 1000.0, 1000.0],
        },
        index=pd.DatetimeIndex(
            [
                "2024-03-05",
                "2024-03-06",
                "2024-03-07",
                "2024-03-08",
                "2024-03-09",
                "2024-03-12",
            ]
        ),
    )


def _es_single_seam(
    *, mode: ContinuousFutureAdjustmentType = DEFAULT_ADJUSTMENT_MODE
) -> tuple[ContinuousFuture, dict[InstrumentId, list[Bar]]]:
    """The ES H4→M4 single-seam fixture (roll 2024-03-07) shared by the request- and
    subscribe-path parity tests: overlapping pre/post leg frames and their native bars."""
    esh4 = InstrumentId(Symbol("ESH4"), Venue("XCME"))
    esm4 = InstrumentId(Symbol("ESM4"), Venue("XCME"))
    pre = _frame(
        ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"],
        [100.0, 101.0, 102.0, 103.0, 104.0],
    )
    post = _frame(
        ["2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11", "2024-03-12"],
        [120.0, 121.0, 122.0, 123.0, 124.0],
    )
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )
    future = continuous_future(
        chain, InstrumentId.from_str("ES.XCME"), adjustment_mode=mode
    )
    return future, {esh4: _bars(esh4, pre), esm4: _bars(esm4, post)}


def test_model_series_is_byte_exact_with_the_literal_ratio_oracle() -> None:
    port = _golden_model_port()
    model = ContinuousContractModel(
        port,
        "ES",
        start="2024-03-01",
        timeframe="1D",
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )

    model.materialize(end="2024-03-13")

    pd.testing.assert_frame_equal(model.frame, _expected_model_ratio_frame())


def test_model_series_is_byte_exact_with_the_literal_spread_oracle() -> None:
    # Same legs, spread algebra: the pre-roll history is shifted by the integer
    # seam delta (+18) instead of scaled — the explicit mode drives the series.
    port = _golden_model_port()
    model = ContinuousContractModel(
        port,
        "ES",
        start="2024-03-01",
        timeframe="1D",
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    )

    model.materialize(end="2024-03-13")

    expected = pd.DataFrame(
        {
            "Open": [117.5, 118.5, 119.5, 120.5, 121.5, 122.5],
            "High": [119.0, 120.0, 121.0, 122.0, 123.0, 124.0],
            "Low": [117.0, 118.0, 119.0, 120.0, 121.0, 122.0],
            "Close": [118.0, 119.0, 120.0, 121.0, 122.0, 123.0],
            "Volume": [1000.0, 1000.0, 1000.0, 100.0, 1000.0, 1000.0],
        },
        index=_expected_model_ratio_frame().index,
    )
    pd.testing.assert_frame_equal(model.frame, expected)


@pytest.mark.parametrize("mode", _MODES)
def test_request_path_series_is_byte_exact_with_the_oracle(mode) -> None:
    esh4 = InstrumentId(Symbol("ESH4"), Venue("XCME"))
    esm4 = InstrumentId(Symbol("ESM4"), Venue("XCME"))
    pre = _frame(
        ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"],
        [100.0, 101.0, 102.0, 103.0, 104.0],
    )
    post = _frame(
        ["2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11", "2024-03-12"],
        [120.0, 121.0, 122.0, 123.0, 124.0],
    )
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )
    future = continuous_future(
        chain, InstrumentId.from_str("ES.XCME"), adjustment_mode=mode
    )
    leg_bars = {esh4: _bars(esh4, pre), esm4: _bars(esm4, post)}

    engine_bars = materialize_continuous_bars(
        future,
        leg_instruments=(_future(esh4), _future(esm4)),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
        end=pd.Timestamp("2024-03-13", tz="UTC"),
    )
    oracle = backward_series(leg_bars, future.transitions, mode=mode)

    engine_raws = [
        (b.open.raw, b.high.raw, b.low.raw, b.close.raw) for b in engine_bars
    ]
    oracle_raws = [
        (o.open_raw, o.high_raw, o.low_raw, o.close_raw)
        for o in oracle[: len(engine_bars)]
    ]
    assert engine_bars  # the request path emitted an adjusted series
    assert (
        engine_raws == oracle_raws
    )  # byte-exact, no tolerance (spread exact; ratio exact at this precision)
    # the first pre-leg close (100.0) carried into the new basis: spread 100 + (121-103); ratio 100 * 121/103
    expected_first = (
        118.0 if mode is ContinuousFutureAdjustmentType.BACKWARD_SPREAD else 117.5
    )
    assert engine_bars[0].close.as_double() == expected_first


@pytest.mark.parametrize("mode", _MODES)
def test_request_path_cumulative_offset_across_three_seams_is_byte_exact(mode) -> None:
    legs = {
        "ESH4.XCME": _frame(
            ["2024-03-04", "2024-03-05", "2024-03-06"], [100.0, 101.0, 102.0]
        ),
        "ESM4.XCME": _frame(
            ["2024-03-06", "2024-03-07", "2024-03-08"], [200.0, 201.0, 202.0]
        ),
        "ESU4.XCME": _frame(
            ["2024-03-08", "2024-03-11", "2024-03-12"], [300.0, 301.0, 302.0]
        ),
        "ESZ4.XCME": _frame(
            ["2024-03-12", "2024-03-13", "2024-03-14"], [400.0, 401.0, 402.0]
        ),
    }
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME", "ESU4.XCME", "ESZ4.XCME"),
        roll_dates=(
            pd.Timestamp("2024-03-06"),
            pd.Timestamp("2024-03-08"),
            pd.Timestamp("2024-03-12"),
        ),
        frames=tuple(legs.values()),
    )
    future = continuous_future(
        chain, InstrumentId.from_str("ES.XCME"), adjustment_mode=mode
    )
    leg_bars = {
        InstrumentId.from_str(sym): _bars(InstrumentId.from_str(sym), fr)
        for sym, fr in legs.items()
    }

    engine_bars = materialize_continuous_bars(
        future,
        leg_instruments=tuple(_future(iid) for iid in leg_bars),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
        end=pd.Timestamp("2024-03-15", tz="UTC"),
    )
    oracle = backward_series(leg_bars, future.transitions, mode=mode)

    engine_raws = [
        (b.open.raw, b.high.raw, b.low.raw, b.close.raw) for b in engine_bars
    ]
    oracle_raws = [
        (o.open_raw, o.high_raw, o.low_raw, o.close_raw)
        for o in oracle[: len(engine_bars)]
    ]
    assert (
        engine_raws == oracle_raws
    )  # byte-exact across three cumulative seams (spread Σ / ratio Π)
    if mode is ContinuousFutureAdjustmentType.BACKWARD_SPREAD:
        closes = [b.close.as_double() for b in engine_bars]
        # Each seam gap is +98 (e.g. 200 - 102); cumulative offsets 294/196/98/0 ramp the
        # spliced series into one continuous +1/day line across all three rolls.
        assert closes[:6] == [394.0, 395.0, 396.0, 397.0, 398.0, 399.0]


@pytest.mark.parametrize("mode", _MODES)
def test_request_path_is_byte_exact_when_bars_sit_on_the_midnight_roll_boundary(
    mode,
) -> None:
    """Real IBKR daily bars are stamped at 00:00 UTC — exactly on the midnight roll
    transition (verified against a live gateway, r8b.2). The seam must then resolve to the
    post leg with no gap or duplicate on the roll day, and stay byte-exact with the oracle for
    either mode. The companion goldens use an off-boundary 21:00 stamp; production sits on it."""
    esh4 = InstrumentId(Symbol("ESH4"), Venue("XCME"))
    esm4 = InstrumentId(Symbol("ESM4"), Venue("XCME"))
    pre = _frame(
        ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"],
        [100.0, 101.0, 102.0, 103.0, 104.0],
    )
    post = _frame(
        ["2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11", "2024-03-12"],
        [120.0, 121.0, 122.0, 123.0, 124.0],
    )
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )
    future = continuous_future(
        chain, InstrumentId.from_str("ES.XCME"), adjustment_mode=mode
    )
    leg_bars = {
        esh4: _bars(esh4, pre, at=time(0, 0)),
        esm4: _bars(esm4, post, at=time(0, 0)),
    }

    engine_bars = materialize_continuous_bars(
        future,
        leg_instruments=(_future(esh4), _future(esm4)),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
        end=pd.Timestamp("2024-03-13", tz="UTC"),
    )
    oracle = backward_series(leg_bars, future.transitions, mode=mode)

    engine_raws = [
        (b.open.raw, b.high.raw, b.low.raw, b.close.raw) for b in engine_bars
    ]
    oracle_raws = [
        (o.open_raw, o.high_raw, o.low_raw, o.close_raw)
        for o in oracle[: len(engine_bars)]
    ]
    ts = [bar.ts_event for bar in engine_bars]
    roll_ns = future.transitions[0].transition_time_ns
    assert engine_bars
    assert engine_raws == oracle_raws  # byte-exact with bars sitting on the boundary
    assert ts == sorted(ts) and len(set(ts)) == len(
        ts
    )  # gap-free order, dupe-free seam
    # The roll day resolves to exactly one bar, owned by the post leg (ESM4 121.0, offset 0)
    # — the pre leg's coincident roll-day bar is not double-counted.
    roll_day = [bar for bar in engine_bars if bar.ts_event == roll_ns]
    assert len(roll_day) == 1
    assert roll_day[0].close.as_double() == 121.0


@pytest.mark.parametrize("mode", _MODES)
def test_subscribe_path_is_byte_exact_with_the_request_path_and_oracle(mode) -> None:
    """AC4 (live half): the live ``subscribe_bars`` roll state machine produces the
    SAME adjusted series as the request path and the Decimal oracle — byte-exact, so
    live ≡ research.  Live runs one bar longer (it emits the final still-forming
    bucket the bounded request stops short of, V2)."""
    future, leg_bars = _es_single_seam(mode=mode)

    request_bars = materialize_continuous_bars(
        future,
        leg_instruments=tuple(_future(iid) for iid in leg_bars),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
        end=pd.Timestamp("2024-03-13", tz="UTC"),
    )
    run = materialize_continuous_bars_via_subscription(
        future,
        leg_instruments=tuple(_future(iid) for iid in leg_bars),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
    )
    oracle = backward_series(leg_bars, future.transitions, mode=mode)

    assert run.bars  # the subscribe path emitted an adjusted live series
    # Live is exactly one bar longer than the bounded request (the final bucket, V2)
    # and spans the full oracle series.
    assert len(run.bars) == len(request_bars) + 1
    assert len(run.bars) == len(oracle)
    # subscribe == oracle byte-exact over the whole live series ...
    assert _raws(run.bars) == _oracle_raws(oracle)
    # ... and subscribe == request byte-exact over their shared overlap.
    assert _raws(run.bars[: len(request_bars)]) == _raws(request_bars)


def test_subscribe_path_rolls_pre_off_post_on_gap_free() -> None:
    """AC3: at the transition the engine deactivates the pre-leg (unsubscribe) then
    activates the post-leg (subscribe + re-apply offset); the spliced live series is
    dupe-free.  The new offset's correctness at the seam is pinned byte-exactly vs the
    request path by the parity test above."""
    future, leg_bars = _es_single_seam()
    esh4, esm4 = tuple(leg_bars)

    run = materialize_continuous_bars_via_subscription(
        future,
        leg_instruments=tuple(_future(iid) for iid in leg_bars),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
    )

    # Segment 0 activated, then per seam: deactivate pre-leg, activate post-leg.
    assert run.roll_events == (
        ("subscribe", esh4),
        ("unsubscribe", esh4),
        ("subscribe", esm4),
    )
    event_ts = [bar.ts_event for bar in run.bars]
    assert len(event_ts) == len(set(event_ts))  # dupe-free across the seam

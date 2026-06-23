"""Spread golden parity: the request-path continuous series is byte-exact (aegis-data).

Path A's gate (AC4, request side): an in-process ``request_bars`` driven by the
roll-transition table the producer builds must reproduce, byte-for-byte, the
``BACKWARD_SPREAD`` continuous series of the independent Decimal oracle.  Spread is
integer-exact, so this is an exact ``==`` over the OHLC raw ints (no tolerance).

The engine stamps each composite bar at its bucket close and drops the final
still-forming bucket, so its series is the head of the oracle's — the parity is
asserted index-aligned over that overlap (prototype ``NOTES.md`` V1/V2/V4).
"""

from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.chain import ContractChain
from aegis_data.continuous_future import continuous_future
from aegis_data.continuous_materialize import materialize_continuous_bars
from tests.support.continuous_spread_oracle import backward_spread_series

_UTC = timezone.utc
_CLOSE = time(21, 0)  # intraday bar stamp, strictly after the midnight roll boundary
_PRECISION = 2


def _frame(dates: list[str], close: list[float]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {"Open": [c - 0.5 for c in close], "High": [c + 1 for c in close],
         "Low": [c - 1 for c in close], "Close": close, "Volume": [100] * len(close)},
        index=idx,
    )


def _future(instrument_id: InstrumentId) -> FuturesContract:
    increment = Price(10 ** -_PRECISION, _PRECISION)
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
        expiration_ns=0,
        ts_event=0,
        ts_init=0,
    )


def _bars(instrument_id: InstrumentId, frame: pd.DataFrame) -> list[Bar]:
    bar_type = raw_bar_type(instrument_id, "1D")
    bars: list[Bar] = []
    for day, row in frame.iterrows():
        ts = int(datetime.combine(day.date(), _CLOSE, _UTC).timestamp() * 1e9)
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


def test_request_path_series_is_byte_exact_with_the_spread_oracle() -> None:
    esh4 = InstrumentId(Symbol("ESH4"), Venue("XCME"))
    esm4 = InstrumentId(Symbol("ESM4"), Venue("XCME"))
    pre = _frame(["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"],
                 [100.0, 101.0, 102.0, 103.0, 104.0])
    post = _frame(["2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11", "2024-03-12"],
                  [120.0, 121.0, 122.0, 123.0, 124.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )
    future = continuous_future(chain, "ES")
    leg_bars = {esh4: _bars(esh4, pre), esm4: _bars(esm4, post)}

    engine_bars = materialize_continuous_bars(
        future,
        leg_instruments=(_future(esh4), _future(esm4)),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
        end=pd.Timestamp("2024-03-13", tz="UTC"),
    )
    oracle = backward_spread_series(leg_bars, future.transitions)

    engine_raws = [(b.open.raw, b.high.raw, b.low.raw, b.close.raw) for b in engine_bars]
    oracle_raws = [(o.open_raw, o.high_raw, o.low_raw, o.close_raw) for o in oracle[: len(engine_bars)]]
    assert engine_bars  # the request path emitted an adjusted series
    assert engine_raws == oracle_raws  # byte-exact, no tolerance
    assert engine_bars[0].close.as_double() == 118.0  # pre leg 100.0 + spread (121 - 103)


def test_request_path_cumulative_offset_across_three_seams_is_byte_exact() -> None:
    legs = {
        "ESH4.XCME": _frame(["2024-03-04", "2024-03-05", "2024-03-06"], [100.0, 101.0, 102.0]),
        "ESM4.XCME": _frame(["2024-03-06", "2024-03-07", "2024-03-08"], [200.0, 201.0, 202.0]),
        "ESU4.XCME": _frame(["2024-03-08", "2024-03-11", "2024-03-12"], [300.0, 301.0, 302.0]),
        "ESZ4.XCME": _frame(["2024-03-12", "2024-03-13", "2024-03-14"], [400.0, 401.0, 402.0]),
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
    future = continuous_future(chain, "ES")
    leg_bars = {InstrumentId.from_str(sym): _bars(InstrumentId.from_str(sym), fr) for sym, fr in legs.items()}

    engine_bars = materialize_continuous_bars(
        future,
        leg_instruments=tuple(_future(iid) for iid in leg_bars),
        leg_bars=leg_bars,
        start=pd.Timestamp("2024-03-01", tz="UTC"),
        end=pd.Timestamp("2024-03-15", tz="UTC"),
    )
    oracle = backward_spread_series(leg_bars, future.transitions)

    engine_raws = [(b.open.raw, b.high.raw, b.low.raw, b.close.raw) for b in engine_bars]
    oracle_raws = [(o.open_raw, o.high_raw, o.low_raw, o.close_raw) for o in oracle[: len(engine_bars)]]
    closes = [b.close.as_double() for b in engine_bars]
    # Each seam gap is +98 (e.g. 200 - 102); cumulative offsets 294/196/98/0 ramp the
    # spliced series into one continuous +1/day line across all three rolls.
    assert closes[:6] == [394.0, 395.0, 396.0, 397.0, 398.0, 399.0]
    assert engine_raws == oracle_raws  # byte-exact across three cumulative seams

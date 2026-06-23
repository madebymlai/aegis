"""Byte-exact ``BACKWARD_SPREAD`` continuous-future oracle (test reference).

An independent Decimal reimplementation of the spread (Panama) arithmetic Nautilus's
``DataEngine`` applies, used by the golden parity test to pin the engine's output
byte-for-byte.  Spread is integer-exact: the cumulative offset is added straight onto
the fixed-point ``PriceRaw`` (scale ``10**16``), so this oracle reproduces the engine's
raw ints with no float drift, at any precision (prototype ``NOTES.md`` V4).

Spread-only — ``BACKWARD_SPREAD`` is the one mode Aegis ships.

Mirrors:
  offset  → ``nautilus_trader/data/engine.pyx :: _continuous_future_compute_offset``
            (backward: cumulative ``Σ_{i∈[k,N)} (post_i − pre_i)``)
  segment → ``:: _continuous_future_next_segment``  (a bar is in segment ``i`` iff its
            ts is ``< transition_i``; past every transition it is the newest segment)
  apply   → ``nautilus_trader/data/aggregation.pyx :: set_adjustment`` (raw add)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.continuous_future import RollTransition

_RAW_SCALE = 10**16  # Nautilus high-precision PriceRaw fixed-point scale


@dataclass(frozen=True)
class AdjustedBar:
    """One adjusted continuous bar as raw fixed-point ints, for byte-exact comparison."""

    ts_event: int
    open_raw: int
    high_raw: int
    low_raw: int
    close_raw: int


def backward_spread_series(
    legs: Mapping[InstrumentId, Sequence[Bar]],
    transitions: Sequence[RollTransition],
) -> list[AdjustedBar]:
    """The ``BACKWARD_SPREAD`` continuous series over ``legs``, in source-ts order.

    Each segment ``k`` (``0..N``) is one leg's active span; its cumulative offset is
    added onto every in-window bar's price raws.  The newest leg (segment ``N``) is the
    unadjusted anchor.  Returns the same head-aligned ordering Nautilus emits (the
    engine additionally stamps each bar at its bucket close and drops the final
    still-forming bucket — the golden test aligns by index over that overlap).
    """
    if not transitions:
        raise ValueError("backward_spread_series needs at least one transition")

    adjusted: list[AdjustedBar] = []
    last = len(transitions)
    for segment in range(last + 1):
        leg_id = (
            transitions[segment].pre_instrument_id
            if segment < last
            else transitions[-1].post_instrument_id
        )
        lo = transitions[segment - 1].transition_time_ns if segment > 0 else None
        hi = transitions[segment].transition_time_ns if segment < last else None
        offset_raw = _to_raw(_segment_offset(transitions, segment))
        for bar in legs.get(leg_id, ()):
            if lo is not None and bar.ts_event < lo:
                continue
            if hi is not None and bar.ts_event >= hi:
                continue
            adjusted.append(
                AdjustedBar(
                    ts_event=bar.ts_event,
                    open_raw=bar.open.raw + offset_raw,
                    high_raw=bar.high.raw + offset_raw,
                    low_raw=bar.low.raw + offset_raw,
                    close_raw=bar.close.raw + offset_raw,
                )
            )
    adjusted.sort(key=lambda b: b.ts_event)
    return adjusted


def _segment_offset(transitions: Sequence[RollTransition], segment: int) -> Decimal:
    """Cumulative backward-spread offset for ``segment``: ``Σ_{i∈[k,N)} (post_i − pre_i)``."""
    offset = Decimal(0)
    for i in range(segment, len(transitions)):
        offset += _decimal(transitions[i].post_price) - _decimal(transitions[i].pre_price)
    return offset


def _decimal(price: float) -> Decimal:
    return Decimal(str(price))


def _to_raw(value: Decimal) -> int:
    return int((value * _RAW_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))

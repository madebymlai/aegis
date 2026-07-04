"""Byte-exact continuous-future oracle (test reference), mode-aware.

An independent Decimal/Price reimplementation of the cumulative-offset + segment-walk arithmetic
Nautilus's ``DataEngine`` applies, used by the golden parity tests to pin the engine's output
byte-for-byte for whichever adjustment mode is in force.

  * **Spread** is integer-exact: the cumulative offset is added straight onto the fixed-point
    ``PriceRaw`` (scale ``10**16``), reproducing the engine's raw ints at any precision.
  * **Ratio** mirrors the engine's float path exactly — the cumulative factor (a ``Decimal`` product
    cast to ``float``, as the engine does) multiplies each price as ``f64`` and is rounded to the
    price's precision via ``Price`` (the same ``price_new`` the engine calls), so it is byte-exact at
    every trading precision (prototype ``NOTES.md`` V4).

Deliberately independent of the production ``rebasing`` module — a parity oracle is an independent
witness of the engine's arithmetic, not a reuse of it.

Mirrors:
  offset/factor → ``nautilus_trader/data/engine.pyx :: _continuous_future_compute_offset``
                  (backward: ``Σ_{i∈[k,N)}(post_i − pre_i)`` for spread; ``Π_{i∈[k,N)}(post_i / pre_i)``
                  for ratio)
  segment       → ``:: _continuous_future_next_segment``  (a bar is in segment ``i`` iff its ts is
                  ``< transition_i``; past every transition it is the newest segment)
  apply         → ``nautilus_trader/data/aggregation.pyx :: set_adjustment`` /
                  ``_apply_adjustment_to_price`` (spread: raw add; ratio: ``Price(f64 * factor, prec)``)
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price

from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE, RollTransition

_RAW_SCALE = 10**16  # Nautilus high-precision PriceRaw fixed-point scale


@dataclass(frozen=True)
class AdjustedBar:
    """One adjusted continuous bar as raw fixed-point ints, for byte-exact comparison."""

    ts_event: int
    open_raw: int
    high_raw: int
    low_raw: int
    close_raw: int


def backward_series(
    legs: Mapping[InstrumentId, Sequence[Bar]],
    transitions: Sequence[RollTransition],
    *,
    mode: ContinuousFutureAdjustmentType = DEFAULT_ADJUSTMENT_MODE,
) -> list[AdjustedBar]:
    """The back-adjusted continuous series over ``legs`` for ``mode``, in source-ts order.

    Each segment ``k`` (``0..N``) is one leg's active span; the newest leg (segment ``N``) is the
    unadjusted anchor.  Returns the same head-aligned ordering Nautilus emits (the engine
    additionally stamps each bar at its bucket close and drops the final still-forming bucket — the
    golden test aligns by index over that overlap).
    """
    if not transitions:
        raise ValueError("backward_series needs at least one transition")

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
        apply = _segment_apply(transitions, segment, mode)
        for bar in legs.get(leg_id, ()):
            if lo is not None and bar.ts_event < lo:
                continue
            if hi is not None and bar.ts_event >= hi:
                continue
            adjusted.append(
                AdjustedBar(
                    ts_event=bar.ts_event,
                    open_raw=apply(bar.open),
                    high_raw=apply(bar.high),
                    low_raw=apply(bar.low),
                    close_raw=apply(bar.close),
                )
            )
    adjusted.sort(key=lambda b: b.ts_event)
    return adjusted


def backward_spread_series(
    legs: Mapping[InstrumentId, Sequence[Bar]],
    transitions: Sequence[RollTransition],
) -> list[AdjustedBar]:
    """Back-compat shim: the ``BACKWARD_SPREAD`` series."""
    return backward_series(
        legs, transitions, mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD
    )


def _segment_apply(
    transitions: Sequence[RollTransition], segment: int, mode: ContinuousFutureAdjustmentType
) -> Callable[[Price], int]:
    """The per-price adjustment for ``segment``, mirroring the engine's hot path for ``mode``."""
    if mode.is_ratio:
        factor = float(_segment_factor(transitions, segment))
        return lambda price: Price(price.as_double() * factor, price.precision).raw
    offset_raw = _to_raw(_segment_offset(transitions, segment))
    return lambda price: price.raw + offset_raw


def _segment_offset(transitions: Sequence[RollTransition], segment: int) -> Decimal:
    """Cumulative backward-spread offset for ``segment``: ``Σ_{i∈[k,N)} (post_i − pre_i)``."""
    offset = Decimal(0)
    for i in range(segment, len(transitions)):
        offset += _decimal(transitions[i].post_price) - _decimal(transitions[i].pre_price)
    return offset


def _segment_factor(transitions: Sequence[RollTransition], segment: int) -> Decimal:
    """Cumulative backward-ratio factor for ``segment``: ``Π_{i∈[k,N)} (post_i / pre_i)``."""
    factor = Decimal(1)
    for i in range(segment, len(transitions)):
        factor *= _decimal(transitions[i].post_price) / _decimal(transitions[i].pre_price)
    return factor


def _decimal(price: float) -> Decimal:
    return Decimal(str(price))


def _to_raw(value: Decimal) -> int:
    return int((value * _RAW_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))

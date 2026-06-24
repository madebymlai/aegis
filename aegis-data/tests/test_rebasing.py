"""Re-basing a recorded value across a continuous-future roll (aegis-rd-iwx).

Behaviour: a ``Rebasing`` carries a price recorded in the pre-roll basis into the post-roll basis,
additively for a spread mode and multiplicatively for a ratio mode — mirroring Nautilus's own
cumulative-offset formulas. The mode is read in one place so flipping it switches the whole live
re-basing (Layer 1 the only switch).
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType

from aegis_data.rebasing import rebasing_between


def _frame(close_by_date: dict[str, float]) -> pd.DataFrame:
    """A continuous OHLCV-style frame carrying only the ``Close`` the re-basing reads."""
    index = pd.DatetimeIndex([pd.Timestamp(day) for day in close_by_date])
    return pd.DataFrame({"Close": list(close_by_date.values())}, index=index)


def test_spread_rebasing_carries_a_pre_roll_close_into_the_new_basis_additively() -> None:
    old = _frame({"2024-06-10": 100.0})
    new = _frame({"2024-06-10": 150.0})  # the roll lifted the whole series by +50 (post - pre)
    rebasing = rebasing_between(old, new, mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD)
    assert rebasing.apply(100.0) == 150.0  # the anchor close lands on the new basis
    assert rebasing.apply(120.0) == 170.0  # additive: every earlier close shifts by the same Δ


def test_ratio_rebasing_carries_a_pre_roll_close_into_the_new_basis_multiplicatively() -> None:
    old = _frame({"2024-06-10": 100.0})
    new = _frame({"2024-06-10": 90.0})  # the roll scaled the whole series by 0.9 (post / pre)
    rebasing = rebasing_between(old, new, mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO)
    assert rebasing.apply(100.0) == 90.0  # the anchor close lands on the new basis
    # multiplicative carry preserves a pre-roll return (an additive carry would not)
    assert rebasing.apply(110.0) / rebasing.apply(100.0) == 110.0 / 100.0


def test_no_seam_overlap_is_a_no_op_rebasing() -> None:
    old = _frame({"2024-06-10": 100.0})
    new = _frame({"2024-09-10": 90.0})  # disjoint indices: no overlapping close to read a shift from
    rebasing = rebasing_between(old, new, mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD)
    assert rebasing.apply(123.0) == 123.0  # nothing to carry -> identity


def test_ratio_rebasing_with_a_non_positive_anchor_price_is_a_no_op() -> None:
    old = _frame({"2024-06-10": 0.0})  # ratio carry needs strictly positive prices (Nautilus)
    new = _frame({"2024-06-10": 90.0})
    rebasing = rebasing_between(old, new, mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO)
    assert rebasing.apply(123.0) == 123.0  # degrade to identity rather than divide by zero


def test_default_mode_reads_the_single_switch_constant() -> None:
    from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE

    old = _frame({"2024-06-10": 100.0})
    new = _frame({"2024-06-10": 90.0})
    # rebasing_between with no mode reads DEFAULT_ADJUSTMENT_MODE — the one constant that also drives
    # the Nautilus series arithmetic, so flipping it switches both together (Layer 1 the only switch).
    assert rebasing_between(old, new).apply(100.0) == (
        rebasing_between(old, new, mode=DEFAULT_ADJUSTMENT_MODE).apply(100.0)
    )

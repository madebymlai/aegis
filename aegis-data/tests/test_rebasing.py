"""The Rebasing carry adapters (aegis-rd-iwx).

Pure primitives: spread adds an offset, ratio multiplies by a factor, identity is a no-op.  The seam
composition that picks among them for a given roll lives on ``ContinuousFuture.rebasing_for_roll`` and is
tested in ``test_continuous_future``.
"""

from __future__ import annotations

from aegis_data.rebasing import IDENTITY, ratio_rebasing, spread_rebasing


def test_spread_rebasing_adds_a_uniform_offset() -> None:
    assert spread_rebasing(50.0).apply(100.0) == 150.0
    assert spread_rebasing(50.0).apply(120.0) == 170.0  # the same Δ shifts every close


def test_ratio_rebasing_multiplies_by_the_factor() -> None:
    assert ratio_rebasing(0.9).apply(100.0) == 90.0
    # a multiplicative carry preserves a pre-roll return (an additive carry would not)
    assert ratio_rebasing(0.9).apply(110.0) / ratio_rebasing(0.9).apply(100.0) == 110.0 / 100.0


def test_identity_rebasing_is_a_no_op() -> None:
    assert IDENTITY.apply(123.0) == 123.0

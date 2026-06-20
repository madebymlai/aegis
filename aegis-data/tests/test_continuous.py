"""Back-adjusted continuous-futures series (aegis-rd-clz.1).

A deep-lookback trend signal computed on a raw stitched front-month series sees a
fake jump at every roll (the basis/roll gap) and a truncated window.  ``back_adjust``
removes the roll gaps — Panama-canal style — so the series is continuous and
within-contract returns are preserved, giving a valid lookback window across rolls.
"""

from __future__ import annotations

import pandas as pd
import pytest

from aegis_data.continuous import back_adjust, roll_adjustment_factors


def _series(dates: list[str], values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.to_datetime(dates), dtype=float)


def test_ratio_back_adjust_removes_roll_gap_and_keeps_recent_contract_unadjusted() -> None:
    # Old contract A and new contract B overlap on the roll date; B trades ~20
    # higher (the basis), so a raw stitch would show a fake jump at the roll.
    a = _series(["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 101.0, 102.0])
    b = _series(["2024-01-02", "2024-01-03", "2024-01-04"], [121.0, 122.0, 123.0])
    roll = pd.Timestamp("2024-01-03")  # the series moves to B on this date

    out = back_adjust([a, b], [roll], method="ratio")

    # The most-recent contract is unadjusted over its active span (date >= roll).
    assert out.loc["2024-01-03"] == 122.0
    assert out.loc["2024-01-04"] == 123.0
    # Ratio scaling is return-neutral: within-A day-over-day returns are preserved.
    assert out.loc["2024-01-02"] / out.loc["2024-01-01"] == pytest.approx(101.0 / 100.0)
    # The seam is continuous: the 01-02→01-03 step reflects A's real move
    # (102/101), NOT the raw ~20% roll jump.
    assert out.loc["2024-01-03"] / out.loc["2024-01-02"] == pytest.approx(102.0 / 101.0)


def test_roll_adjustment_factors_expose_per_contract_multipliers() -> None:
    # The factors let a caller apply ONE Close-derived adjustment across O/H/L/C.
    a = _series(["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 101.0, 102.0])
    b = _series(["2024-01-02", "2024-01-03", "2024-01-04"], [121.0, 122.0, 123.0])
    roll = pd.Timestamp("2024-01-03")

    factors = roll_adjustment_factors([a, b], [roll], method="ratio")

    # Newest contract is identity; the older is scaled by the seam ratio 122/102.
    assert factors[1] == 1.0
    assert factors[0] == pytest.approx(122.0 / 102.0)


def test_factors_match_nautilus_backward_ratio_published_vectors() -> None:
    # Tripwire pinning our math to NautilusTrader's own test vectors so research and live
    # cannot drift from the BACKWARD_RATIO definition (no Nautilus dependency, just the
    # numbers). Source: nautilus_trader crates/data/src/engine/requests.rs
    # test_continuous_future_adjustment_for_backward_ratio — transitions (pre 100 -> post
    # 200), (pre 50 -> post 150) yield per-segment factors [6, 3, 1] (newest unadjusted).
    c0 = _series(["2024-03-01"], [100.0])  # roll0 pre
    c1 = _series(["2024-03-01", "2024-06-01"], [200.0, 50.0])  # roll0 post, roll1 pre
    c2 = _series(["2024-06-01"], [150.0])  # roll1 post
    rolls = [pd.Timestamp("2024-03-01"), pd.Timestamp("2024-06-01")]

    factors = roll_adjustment_factors([c0, c1, c2], rolls, method="ratio")

    assert factors == pytest.approx((6.0, 3.0, 1.0))


def test_factors_match_nautilus_backward_spread_published_vectors() -> None:
    # As above for BACKWARD_SPREAD (additive). Nautilus' spread test asserts per-segment
    # offsets [40, 30, 0]; reproduced here with transition diffs (post-pre) of +10 then +30
    # (newest unadjusted), matching our cumulative sum-of-(new-old).
    c0 = _series(["2024-03-01"], [100.0])  # roll0 pre
    c1 = _series(["2024-03-01", "2024-06-01"], [110.0, 50.0])  # roll0 post (+10), roll1 pre
    c2 = _series(["2024-06-01"], [80.0])  # roll1 post (+30)
    rolls = [pd.Timestamp("2024-03-01"), pd.Timestamp("2024-06-01")]

    factors = roll_adjustment_factors([c0, c1, c2], rolls, method="difference")

    assert factors == pytest.approx((40.0, 30.0, 0.0))


def test_difference_back_adjust_shifts_history_additively() -> None:
    a = _series(["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 101.0, 102.0])
    b = _series(["2024-01-02", "2024-01-03", "2024-01-04"], [121.0, 122.0, 123.0])
    roll = pd.Timestamp("2024-01-03")

    out = back_adjust([a, b], [roll], method="difference")

    # Most-recent contract unadjusted.
    assert out.loc["2024-01-03"] == 122.0
    assert out.loc["2024-01-04"] == 123.0
    # Additive shift (gap = 122 - 102 = 20) lifts history; absolute differences kept.
    assert out.loc["2024-01-01"] == pytest.approx(120.0)
    assert out.loc["2024-01-02"] == pytest.approx(121.0)
    # Seam continuous additively: 01-02→01-03 step = A's real +1, not the +20 gap.
    assert out.loc["2024-01-03"] - out.loc["2024-01-02"] == pytest.approx(1.0)


def test_three_contract_chain_compounds_adjustments_at_every_seam() -> None:
    # Three contracts, two rolls; each later contract trades ~100 higher.
    a = _series(["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 101.0, 102.0])
    b = _series(["2024-01-03", "2024-01-04", "2024-01-05"], [201.0, 202.0, 203.0])
    c = _series(["2024-01-05", "2024-01-06"], [301.0, 302.0])
    roll_ab = pd.Timestamp("2024-01-03")  # A→B
    roll_bc = pd.Timestamp("2024-01-05")  # B→C

    out = back_adjust([a, b, c], [roll_ab, roll_bc], method="ratio")

    # Newest contract unadjusted.
    assert out.loc["2024-01-05"] == 301.0
    assert out.loc["2024-01-06"] == 302.0
    # Every seam is continuous (reflects the real move of the older contract,
    # not the ~100-point roll gap):
    assert out.loc["2024-01-05"] / out.loc["2024-01-04"] == pytest.approx(203.0 / 202.0)  # B's move
    assert out.loc["2024-01-03"] / out.loc["2024-01-02"] == pytest.approx(102.0 / 101.0)  # A's move
    # Within the oldest span, returns survive the compounded adjustment.
    assert out.loc["2024-01-02"] / out.loc["2024-01-01"] == pytest.approx(101.0 / 100.0)
    # The full series is strictly increasing — no gaps anywhere.
    assert out.sort_index().is_monotonic_increasing


def test_single_contract_is_returned_unchanged() -> None:
    a = _series(["2024-01-01", "2024-01-02"], [100.0, 101.0])

    out = back_adjust([a], [], method="ratio")

    pd.testing.assert_series_equal(out, a)


def test_missing_roll_overlap_fails_closed() -> None:
    a = _series(["2024-01-01", "2024-01-02"], [100.0, 101.0])
    b = _series(["2024-01-03", "2024-01-04"], [200.0, 201.0])  # no shared roll-day price
    roll = pd.Timestamp("2024-01-02")  # in A but not B

    with pytest.raises(ValueError, match="overlap"):
        back_adjust([a, b], [roll], method="ratio")


def test_unknown_method_fails_closed() -> None:
    a = _series(["2024-01-01", "2024-01-02"], [100.0, 101.0])
    b = _series(["2024-01-02", "2024-01-03"], [200.0, 201.0])

    with pytest.raises(ValueError, match="method"):
        back_adjust([a, b], [pd.Timestamp("2024-01-02")], method="panama")


def test_empty_contracts_fails_closed() -> None:
    with pytest.raises(ValueError, match="at least one contract"):
        back_adjust([], [], method="ratio")


def test_roll_dates_length_must_match_seams() -> None:
    a = _series(["2024-01-01", "2024-01-02"], [100.0, 101.0])
    b = _series(["2024-01-02", "2024-01-03"], [200.0, 201.0])

    with pytest.raises(ValueError, match="roll date"):
        back_adjust([a, b], [], method="ratio")  # one seam needs one roll date

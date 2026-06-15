"""Unit tests for the pure diagonal risk-budget allocator."""

from __future__ import annotations

import pytest

from aegis_trader.domain.allocator import (
    allocate_diagonal_vol_target,
    diagonal_book_vol,
)
from aegis_trader.domain.types import SleeveName

_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")


def test_equal_vols_make_multipliers_track_risk_shares():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {"A": 1.0}, _CARRY: {"B": 1.0}},
        risk_shares={_TREND: 0.75, _CARRY: 0.25},
        realized_vols={_TREND: 0.10, _CARRY: 0.10},
        book_vol_target=0.09,
    )

    ratio = allocation.multipliers[_TREND] / allocation.multipliers[_CARRY]
    assert ratio == pytest.approx(3.0)


def test_higher_vol_sleeve_is_scaled_down_to_hold_its_share():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {"A": 1.0}, _CARRY: {"B": 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.20},
        book_vol_target=0.10,
    )

    assert allocation.multipliers[_CARRY] == pytest.approx(
        allocation.multipliers[_TREND] / 2.0
    )


def test_diagonal_book_hits_vol_target():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {"A": 1.0}, _CARRY: {"B": 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.20},
        book_vol_target=0.09,
    )

    assert diagonal_book_vol(
        allocation.multipliers,
        {_TREND: 0.10, _CARRY: 0.20},
    ) == pytest.approx(0.09)


def test_missing_or_zero_vol_fails_closed():
    with pytest.raises(ValueError, match="missing realized vol"):
        allocate_diagonal_vol_target(
            sleeve_targets={_TREND: {"A": 1.0}, _CARRY: {"B": 1.0}},
            risk_shares={_TREND: 0.5, _CARRY: 0.5},
            realized_vols={_TREND: 0.10},
            book_vol_target=0.09,
        )

    with pytest.raises(ValueError, match="degenerate realized vol"):
        allocate_diagonal_vol_target(
            sleeve_targets={_TREND: {"A": 1.0}},
            risk_shares={_TREND: 1.0},
            realized_vols={_TREND: 0.0},
            book_vol_target=0.09,
        )


def test_warmup_without_vols_falls_back_to_raw_risk_share():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {"A": 0.5}, _CARRY: {"B": -0.25}},
        risk_shares={_TREND: 0.6, _CARRY: 0.4},
        realized_vols=None,
        book_vol_target=0.09,
    )

    assert allocation.scaled_targets[_TREND]["A"] == pytest.approx(0.30)
    assert allocation.scaled_targets[_CARRY]["B"] == pytest.approx(-0.10)

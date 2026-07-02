"""Unit tests for the pure diagonal risk-budget allocator."""

from __future__ import annotations

import pytest

from aegis_trader.domain.allocator import (
    SleeveWeightBand,
    allocate_covariance_vol_target,
    allocate_diagonal_vol_target,
    covariance_book_vol,
    diagonal_book_vol,
    equal_risk_contribution_weights,
    portfolio_skew,
    risk_contribution_shares,
)
from aegis_trader.domain.book_config import DrawdownDeleverCurve
from aegis_trader.domain.types import SleeveName
from nautilus_trader.model.identifiers import InstrumentId


def _iid(symbol: str) -> InstrumentId:
    return InstrumentId.from_str(f"{symbol}.TEST")


_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")
_TAIL = SleeveName("tail")


def test_equal_vols_make_multipliers_track_risk_shares():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
        risk_shares={_TREND: 0.75, _CARRY: 0.25},
        realized_vols={_TREND: 0.10, _CARRY: 0.10},
        book_vol_target=0.09,
    )

    ratio = allocation.multipliers[_TREND] / allocation.multipliers[_CARRY]
    assert ratio == pytest.approx(3.0)


def test_higher_vol_sleeve_is_scaled_down_to_hold_its_share():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.20},
        book_vol_target=0.10,
    )

    assert allocation.multipliers[_CARRY] == pytest.approx(
        allocation.multipliers[_TREND] / 2.0
    )


def test_diagonal_book_hits_vol_target():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
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
            sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
            risk_shares={_TREND: 0.5, _CARRY: 0.5},
            realized_vols={_TREND: 0.10},
            book_vol_target=0.09,
        )

    with pytest.raises(ValueError, match="degenerate realized vol"):
        allocate_diagonal_vol_target(
            sleeve_targets={_TREND: {_iid("A"): 1.0}},
            risk_shares={_TREND: 1.0},
            realized_vols={_TREND: 0.0},
            book_vol_target=0.09,
        )


def test_warmup_without_vols_falls_back_to_raw_risk_share():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 0.5}, _CARRY: {_iid("B"): -0.25}},
        risk_shares={_TREND: 0.6, _CARRY: 0.4},
        realized_vols=None,
        book_vol_target=0.09,
    )

    assert allocation.scaled_targets[_TREND][_iid("A")] == pytest.approx(0.30)
    assert allocation.scaled_targets[_CARRY][_iid("B")] == pytest.approx(-0.10)


def test_covariance_zero_correlation_reproduces_diagonal_result():
    sleeve_targets = {_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}}
    risk_shares = {_TREND: 0.75, _CARRY: 0.25}
    vols = {_TREND: 0.10, _CARRY: 0.20}
    diagonal = allocate_diagonal_vol_target(
        sleeve_targets=sleeve_targets,
        risk_shares=risk_shares,
        realized_vols=vols,
        book_vol_target=0.09,
    )

    covariance = allocate_covariance_vol_target(
        sleeve_targets=sleeve_targets,
        risk_shares=risk_shares,
        realized_covariance={
            _TREND: {_TREND: 0.10**2, _CARRY: 0.0},
            _CARRY: {_TREND: 0.0, _CARRY: 0.20**2},
        },
        book_vol_target=0.09,
    )

    assert covariance.multipliers[_TREND] == pytest.approx(diagonal.multipliers[_TREND])
    assert covariance.multipliers[_CARRY] == pytest.approx(diagonal.multipliers[_CARRY])


def test_correlated_sleeves_receive_smaller_combined_weight_than_uncorrelated():
    sleeve_targets = {_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}}
    risk_shares = {_TREND: 0.5, _CARRY: 0.5}
    uncorrelated = allocate_covariance_vol_target(
        sleeve_targets=sleeve_targets,
        risk_shares=risk_shares,
        realized_covariance={
            _TREND: {_TREND: 0.10**2, _CARRY: 0.0},
            _CARRY: {_TREND: 0.0, _CARRY: 0.10**2},
        },
        book_vol_target=0.09,
    )
    correlated = allocate_covariance_vol_target(
        sleeve_targets=sleeve_targets,
        risk_shares=risk_shares,
        realized_covariance={
            _TREND: {_TREND: 0.10**2, _CARRY: 0.90 * 0.10 * 0.10},
            _CARRY: {_TREND: 0.90 * 0.10 * 0.10, _CARRY: 0.10**2},
        },
        book_vol_target=0.09,
    )

    assert sum(correlated.multipliers.values()) < sum(uncorrelated.multipliers.values())
    assert covariance_book_vol(correlated.multipliers, {
        _TREND: {_TREND: 0.10**2, _CARRY: 0.90 * 0.10 * 0.10},
        _CARRY: {_TREND: 0.90 * 0.10 * 0.10, _CARRY: 0.10**2},
    }) == pytest.approx(0.09)


def test_top_down_group_split_prevents_correlated_cluster_dominating_book_risk():
    groups = {_TREND: "Floor", _CARRY: "Floor", _TAIL: "Target"}
    covariance = {
        _TREND: {_TREND: 0.10**2, _CARRY: 0.95 * 0.10 * 0.10, _TAIL: 0.0},
        _CARRY: {_TREND: 0.95 * 0.10 * 0.10, _CARRY: 0.10**2, _TAIL: 0.0},
        _TAIL: {_TREND: 0.0, _CARRY: 0.0, _TAIL: 0.10**2},
    }

    allocation = allocate_covariance_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}, _TAIL: {_iid("C"): 1.0}},
        risk_shares={_TREND: 0.25, _CARRY: 0.25, _TAIL: 0.5},
        realized_covariance=covariance,
        book_vol_target=0.09,
        groups=groups,
    )

    rc = risk_contribution_shares(allocation.multipliers, covariance)
    floor_risk = rc[_TREND] + rc[_CARRY]
    target_risk = rc[_TAIL]
    assert floor_risk == pytest.approx(target_risk, abs=2e-3)
    assert floor_risk < 0.55


def test_sleeve_weight_band_suppresses_inside_band_churn():
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.101},
        book_vol_target=0.09,
        previous_multipliers={_TREND: 0.6363961030678927, _CARRY: 0.6363961030678927},
        sleeve_weight_bands={
            _TREND: SleeveWeightBand(down=0.01, up=0.01),
            _CARRY: SleeveWeightBand(down=0.01, up=0.01),
        },
        sleeve_reversion_fraction=0.5,
    )

    assert allocation.multipliers[_TREND] == pytest.approx(0.6363961030678927)
    assert allocation.multipliers[_CARRY] == pytest.approx(0.6363961030678927)
    assert allocation.scaled_targets[_CARRY][_iid("B")] == pytest.approx(0.6363961030678927)


def test_sleeve_weight_band_reverts_partially_after_breach():
    previous = 0.6363961030678927
    full_target = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.102},
        book_vol_target=0.09,
    )

    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.102},
        book_vol_target=0.09,
        previous_multipliers={_TREND: previous, _CARRY: previous},
        sleeve_weight_bands={
            _TREND: SleeveWeightBand(down=0.01, up=0.01),
            _CARRY: SleeveWeightBand(down=0.01, up=0.01),
        },
        sleeve_reversion_fraction=0.5,
    )

    assert allocation.multipliers[_TREND] == pytest.approx(previous)
    assert allocation.multipliers[_CARRY] == pytest.approx(
        previous + 0.5 * (full_target.multipliers[_CARRY] - previous)
    )
    assert allocation.multipliers[_CARRY] != pytest.approx(full_target.multipliers[_CARRY])


def test_portfolio_skew_measures_realized_convexity_of_the_weighted_book_stream():
    # Left-skewed (occasional large loss) -> net-concave -> negative skew.
    concave = (0.01, 0.01, 0.01, 0.01, -0.20, 0.01, 0.01, 0.01)
    # Right-skewed (occasional large gain) -> net-convex -> positive skew.
    convex = tuple(-r for r in concave)

    assert portfolio_skew({_TREND: 1.0}, {_TREND: concave}) < 0.0
    assert portfolio_skew({_TREND: 1.0}, {_TREND: convex}) > 0.0


def test_portfolio_skew_is_zero_for_an_empty_or_flat_stream():
    # A measurement, not a constraint: routine no-data / no-dispersion cases are
    # not errors — they are "no measurable skew" (0.0), so callers never guard.
    assert portfolio_skew({}, {}) == 0.0
    assert portfolio_skew({_TREND: 1.0}, {_TREND: (0.01, 0.01, 0.01, 0.01)}) == 0.0


def test_drawdown_delever_scales_exposure_monotonically_and_recovers():
    curve = DrawdownDeleverCurve(
        start_drawdown=0.05,
        end_drawdown=0.25,
        floor_multiplier=0.40,
    )

    no_drawdown = _drawdown_delevered_gross_exposure(curve, drawdown=0.00)
    mild_drawdown = _drawdown_delevered_gross_exposure(curve, drawdown=0.10)
    deep_drawdown = _drawdown_delevered_gross_exposure(curve, drawdown=0.20)
    floor_drawdown = _drawdown_delevered_gross_exposure(curve, drawdown=0.25)
    recovered_to_mild = _drawdown_delevered_gross_exposure(curve, drawdown=0.10)
    fully_recovered = _drawdown_delevered_gross_exposure(curve, drawdown=0.00)

    assert no_drawdown > mild_drawdown > deep_drawdown > floor_drawdown
    assert recovered_to_mild == pytest.approx(mild_drawdown)
    assert fully_recovered == pytest.approx(no_drawdown)


def _drawdown_delevered_gross_exposure(
    curve: DrawdownDeleverCurve,
    *,
    drawdown: float,
) -> float:
    allocation = allocate_diagonal_vol_target(
        sleeve_targets={_TREND: {_iid("A"): 1.0}, _CARRY: {_iid("B"): 1.0}},
        risk_shares={_TREND: 0.5, _CARRY: 0.5},
        realized_vols={_TREND: 0.10, _CARRY: 0.10},
        book_vol_target=0.09,
        realized_drawdown=drawdown,
        drawdown_delever_curve=curve,
    )
    return sum(abs(multiplier) for multiplier in allocation.multipliers.values())


def test_multi_name_default_equal_risk_contribution_scales_high_vol_name_down():
    weights = equal_risk_contribution_weights(
        {
            "LOW_VOL": {"LOW_VOL": 0.10**2, "HIGH_VOL": 0.0},
            "HIGH_VOL": {"LOW_VOL": 0.0, "HIGH_VOL": 0.20**2},
        }
    )

    assert weights["HIGH_VOL"] == pytest.approx(weights["LOW_VOL"] / 2.0)
    assert sum(weights.values()) == pytest.approx(1.0)

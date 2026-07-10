"""Rebalance behavior at the pipeline seam.

Every test stages a weight-space book through fake Execution Bundles and drives
``RebalancePipeline.rebalance_period``, asserting only production observables:
orders, halt reason, gate outcome, summary counts, and applied sleeve weights.
The identity-sizing convention (bars at 1.0, NAV 1,000,000) makes a weight
delta ``w`` read back as an order quantity of ``w * 1_000_000``.

Cross-sleeve instrument overlap is not staged anywhere: book assembly rejects
two sleeves declaring one instrument (each bundle must band exactly its own
contract), so overlap netting is unreachable from the production interface.
"""

from __future__ import annotations

import pytest

from aegis_runtime import DriftBand
from aegis_trader.domain.book_config import DrawdownDeleverCurve
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.trader.pipeline import GateOutcome
from tests.support.rebalance_harness import (
    SleeveSpec,
    StagedLedger,
    build_harness,
    signed_order_weights,
)


def test_disjoint_sleeves_scale_by_risk_share_into_one_plan() -> None:
    harness = build_harness(
        [
            SleeveSpec("trend", 0.6, {"AAA": 0.5}),
            SleeveSpec("carry", 0.4, {"BBB": -0.3}),
        ]
    )

    result = harness.run()

    assert signed_order_weights(result) == {
        "AAA": pytest.approx(0.30),
        "BBB": pytest.approx(-0.12),
    }
    assert [order.instrument_id.symbol.value for order in result.orders] == ["AAA", "BBB"]
    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.summary.num_orders == 2
    assert result.halt_reason is None


def test_drift_band_holds_the_realized_position() -> None:
    harness = build_harness(
        [
            SleeveSpec(
                "trend", 1.0, {"AAA": 0.50}, bands={"AAA": DriftBand.symmetric(0.02)}
            )
        ],
        realized={"AAA": 0.51},
    )

    result = harness.run()

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.halt_reason is None


def test_drift_band_trips_outside_the_band() -> None:
    harness = build_harness(
        [
            SleeveSpec(
                "trend", 1.0, {"AAA": 0.50}, bands={"AAA": DriftBand.symmetric(0.02)}
            )
        ],
        realized={"AAA": 0.55},
    )

    result = harness.run()

    assert result.orders[0].side == OrderSide.SELL
    assert result.orders[0].quantity == pytest.approx(50_000.0)
    assert result.summary.num_orders == 1


def test_unfixable_per_name_breach_returns_no_orders_and_halts() -> None:
    harness = build_harness(
        [
            SleeveSpec(
                "trend", 1.0, {"AAA": 0.15}, bands={"AAA": DriftBand.symmetric(0.10)}
            )
        ],
        realized={"AAA": 0.15},
        per_name_cap=0.10,
    )

    result = harness.run()

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_reason is not None
    assert "AAA.TEST" in result.halt_reason
    assert "unfixable" in result.halt_reason


def test_net_cap_breach_returns_no_orders_and_halts() -> None:
    harness = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.15, "BBB": -0.01})],
        net_cap=0.10,
    )

    result = harness.run()

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_reason is not None
    assert "exceeds net_cap" in result.halt_reason


def test_gross_clamp_scales_the_target_book_to_the_ceiling() -> None:
    harness = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.6, "BBB": 0.6})],
        gross_cap=0.6,
    )

    result = harness.run()

    assert signed_order_weights(result) == {
        "AAA": pytest.approx(0.30),
        "BBB": pytest.approx(0.30),
    }
    assert result.summary.gate_outcome == GateOutcome.PASS


def test_applied_sleeve_weights_band_the_next_periods_allocation() -> None:
    """The memory loop: period 1's applied sleeve weights are the anchor of
    period 2's sleeve no-churn band, so a vol shift inside the band leaves the
    applied weights exactly where period 1 put them."""
    low, high = SleeveName("low"), SleeveName("high")
    flat = {
        low: {low: 0.10**2, high: 0.0},
        high: {low: 0.0, high: 0.10**2},
    }
    shifted = {
        low: {low: 0.10**2, high: 0.0},
        high: {low: 0.0, high: 0.30**2},
    }
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"LOW": 1.0}, weight_band=0.5),
            SleeveSpec("high", 0.5, {"HIGH": 1.0}, weight_band=0.5),
        ],
        ledger=StagedLedger(covariances=[flat, shifted]),
        book_vol_target=0.10,
        gross_cap=2.0,
    )

    first = harness.run()
    applied_after_first = harness.pipeline.last_sleeve_weights
    second = harness.run()
    applied_after_second = harness.pipeline.last_sleeve_weights

    assert first.summary.gate_outcome == GateOutcome.PASS
    assert second.summary.gate_outcome == GateOutcome.PASS
    assert applied_after_first == {
        low: pytest.approx(0.7071067811865476),
        high: pytest.approx(0.7071067811865476),
    }
    # The shifted covariance alone would re-solve `high` down to ~0.2357; the
    # sleeve band (0.5) absorbs that drift and holds period 1's applied weight.
    assert applied_after_second == applied_after_first


def test_sleeve_band_trip_reallocates_to_the_fresh_solve() -> None:
    """The complement of the hold: a vol shift beyond the sleeve band moves the
    applied weight to the fresh covariance solve (full reversion by default)."""
    low, high = SleeveName("low"), SleeveName("high")
    flat = {
        low: {low: 0.10**2, high: 0.0},
        high: {low: 0.0, high: 0.10**2},
    }
    shifted = {
        low: {low: 0.10**2, high: 0.0},
        high: {low: 0.0, high: 0.30**2},
    }
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"LOW": 1.0}, weight_band=0.01),
            SleeveSpec("high", 0.5, {"HIGH": 1.0}, weight_band=0.01),
        ],
        ledger=StagedLedger(covariances=[flat, shifted]),
        book_vol_target=0.10,
        gross_cap=2.0,
    )

    harness.run()
    harness.run()
    applied = harness.pipeline.last_sleeve_weights

    assert applied == {
        low: pytest.approx(0.7071067811865476),
        high: pytest.approx(0.2357022603955158),
    }


# ---------------------------------------------------------------------------
# Single sleeve: targets become orders through allocator scaling and sizing
# ---------------------------------------------------------------------------


def test_single_instrument_buy() -> None:
    result = build_harness([SleeveSpec("trend", 1.0, {"AAA": 0.5})]).run()

    assert result.orders[0].instrument_id.symbol.value == "AAA"
    assert result.orders[0].side == OrderSide.BUY
    assert result.orders[0].quantity == pytest.approx(500_000.0)
    assert result.summary.num_orders == 1


def test_single_instrument_sell() -> None:
    result = build_harness([SleeveSpec("trend", 1.0, {"AAA": -0.3})]).run()

    assert result.orders[0].side == OrderSide.SELL
    assert result.orders[0].quantity == pytest.approx(300_000.0)


def test_risk_share_scales_the_sleeve_target() -> None:
    result = build_harness([SleeveSpec("trend", 0.5, {"AAA": 0.5})]).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(0.25)}


def test_zero_target_weight_emits_no_order() -> None:
    result = build_harness([SleeveSpec("trend", 1.0, {"AAA": 0.0})]).run()

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.PASS


def test_near_zero_target_weight_emits_no_order() -> None:
    result = build_harness([SleeveSpec("trend", 1.0, {"AAA": 1e-13})]).run()

    assert result.orders == ()


def test_multiple_instruments_trade_independently() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.4, "BBB": -0.2})]
    ).run()

    assert signed_order_weights(result) == {
        "AAA": pytest.approx(0.4),
        "BBB": pytest.approx(-0.2),
    }


def test_latest_target_row_wins() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.5}, rows=({"AAA": 0.1},))]
    ).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(0.5)}


def test_sleeve_without_bars_holds_without_aborting_the_book() -> None:
    result = build_harness(
        [
            SleeveSpec("trend", 0.5, {"AAA": 0.4}),
            SleeveSpec("carry", 0.5, {"BBB": 0.3}, stale=True),
        ]
    ).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(0.20)}
    assert result.summary.num_sleeves == 1


def test_zero_risk_share_sleeve_contributes_nothing_during_warmup() -> None:
    result = build_harness(
        [
            SleeveSpec("trend", 0.6, {"AAA": 0.5}),
            SleeveSpec("carry", 0.0, {"BBB": 0.8}),
        ]
    ).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(0.30)}


# ---------------------------------------------------------------------------
# Covariance-driven allocation (the ledger is the production estimate source)
# ---------------------------------------------------------------------------


def _diagonal_covariance(vols: dict[str, float]) -> dict[SleeveName, dict[SleeveName, float]]:
    names = {symbol: SleeveName(symbol) for symbol in vols}
    return {
        names[row]: {
            names[col]: (vols[row] ** 2 if row == col else 0.0) for col in vols
        }
        for row in vols
    }


def test_higher_vol_sleeve_is_scaled_down_before_netting() -> None:
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"LOW": 1.0}),
            SleeveSpec("high", 0.5, {"HIGH": 1.0}),
        ],
        ledger=StagedLedger(
            covariances=[_diagonal_covariance({"low": 0.10, "high": 0.20})]
        ),
        book_vol_target=0.10,
        gross_cap=2.0,
    )

    result = harness.run()

    assert signed_order_weights(result) == {
        "LOW": pytest.approx(0.7071067811865476, abs=1e-6),
        "HIGH": pytest.approx(0.3535533905932738, abs=1e-6),
    }


def test_correlated_sleeves_are_scaled_down_harder_than_uncorrelated() -> None:
    def _covariance(rho: float) -> dict[SleeveName, dict[SleeveName, float]]:
        low, high = SleeveName("low"), SleeveName("high")
        return {
            low: {low: 0.10**2, high: rho * 0.10 * 0.10},
            high: {low: rho * 0.10 * 0.10, high: 0.10**2},
        }

    def _gross(rho: float) -> float:
        harness = build_harness(
            [
                SleeveSpec("low", 0.5, {"LOW": 1.0}),
                SleeveSpec("high", 0.5, {"HIGH": 1.0}),
            ],
            ledger=StagedLedger(covariances=[_covariance(rho)]),
            book_vol_target=0.05,
        )
        return sum(abs(weight) for weight in signed_order_weights(harness.run()).values())

    assert _gross(0.0) == pytest.approx(0.7071067811865476, abs=1e-6)
    assert _gross(0.9) == pytest.approx(0.5129891760425771, abs=1e-6)


# ---------------------------------------------------------------------------
# Drift bands on the realized book
# ---------------------------------------------------------------------------


def test_band_holds_at_the_inclusive_boundary() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.50}, bands={"AAA": DriftBand.symmetric(0.02)})],
        realized={"AAA": 0.52},
    ).run()

    assert result.orders == ()


def test_band_trades_to_an_interior_destination() -> None:
    band = DriftBand(up=0.02, down=0.02, destination_fraction=0.5)
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.50}, bands={"AAA": band})],
        realized={"AAA": 0.55},
    ).run()

    # resolved = target + (1 - 0.5) * up = 0.51; delta = 0.51 - 0.55.
    assert signed_order_weights(result) == {"AAA": pytest.approx(-0.04)}


def test_asymmetric_band_gates_each_tail_by_its_own_width() -> None:
    band = DriftBand(up=0.01, down=0.05)
    sleeves = [SleeveSpec("trend", 1.0, {"TAIL": 0.50}, bands={"TAIL": band})]

    above = build_harness(sleeves, realized={"TAIL": 0.52}).run()
    below = build_harness(sleeves, realized={"TAIL": 0.48}).run()

    assert signed_order_weights(above) == {"TAIL": pytest.approx(-0.02)}
    assert below.orders == ()


def test_sub_band_new_position_is_gated() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.01}, bands={"AAA": DriftBand.symmetric(0.02)})]
    ).run()

    assert result.orders == ()


def test_new_position_opens_when_outside_the_band() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.03}, bands={"AAA": DriftBand.symmetric(0.02)})]
    ).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(0.03)}


def test_orders_emit_in_deterministic_instrument_order() -> None:
    """Reproducibility (aegis-rd-10d): the order-submission sequence is stable
    id-sorted, never the hash-seed-dependent union order."""
    # BBB is a declared instrument the sleeve no longer wants (target 0): the
    # pipeline can only trade instruments some bundle declares.
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"CCC": 0.20, "AAA": 0.20, "DDD": 0.20, "BBB": 0.0})],
        realized={"BBB": 0.20, "AAA": 0.05},
    ).run()

    assert [order.instrument_id.symbol.value for order in result.orders] == [
        "AAA",
        "BBB",
        "CCC",
        "DDD",
    ]
    assert signed_order_weights(result) == {
        "AAA": pytest.approx(0.15),
        "BBB": pytest.approx(-0.20),
        "CCC": pytest.approx(0.20),
        "DDD": pytest.approx(0.20),
    }


def test_bundle_band_scales_with_the_owning_sleeves_multiplier() -> None:
    """Regression (aegis-rd-reyj defect 2): the band gates at the sleeve's book
    scale, so a cold-book multiplier below one still lets the position open."""
    result = build_harness(
        [
            SleeveSpec("floor", 0.25, {"AAA": 0.20}, bands={"AAA": DriftBand.symmetric(0.10)}),
            SleeveSpec("rest", 0.75, {"BBB": 0.20}, bands={"BBB": DriftBand.symmetric(0.10)}),
        ]
    ).run()

    assert signed_order_weights(result) == {
        "AAA": pytest.approx(0.05),
        "BBB": pytest.approx(0.15),
    }


def test_scaled_band_still_suppresses_within_band_drift() -> None:
    sleeves = [
        SleeveSpec("floor", 0.25, {"AAA": 0.20}, bands={"AAA": DriftBand.symmetric(0.10)}),
        SleeveSpec("rest", 0.75, {"BBB": 0.20}, bands={"BBB": DriftBand.symmetric(0.10)}),
    ]

    # Scaled targets: AAA 0.05 (band 0.025), BBB 0.15 (band 0.075).
    inside = build_harness(sleeves, realized={"AAA": 0.04, "BBB": 0.15}).run()
    outside = build_harness(sleeves, realized={"AAA": 0.02, "BBB": 0.15}).run()

    assert inside.orders == ()
    assert signed_order_weights(outside) == {"AAA": pytest.approx(0.03)}


# ---------------------------------------------------------------------------
# Per-name cap: widen-to-compliance, then fail closed
# ---------------------------------------------------------------------------


def test_band_tripped_corrective_also_clears_the_per_name_breach() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.08}, bands={"AAA": DriftBand.symmetric(0.02)})],
        realized={"AAA": 0.12},
        per_name_cap=0.10,
    ).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(-0.04)}
    assert result.summary.gate_outcome == GateOutcome.PASS


def test_band_suppressed_breach_widens_to_the_cap_boundary() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.08}, bands={"AAA": DriftBand.symmetric(0.10)})],
        realized={"AAA": 0.12},
        per_name_cap=0.10,
    ).run()

    # The band holds the drift, so the gate widens to the cap, not the target.
    assert signed_order_weights(result) == {"AAA": pytest.approx(-0.02)}


def test_short_position_breach_widens_back_to_the_negative_cap() -> None:
    result = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": -0.08}, bands={"AAA": DriftBand.symmetric(0.10)})],
        realized={"AAA": -0.12},
        per_name_cap=0.10,
    ).run()

    assert signed_order_weights(result) == {"AAA": pytest.approx(0.02)}


# ---------------------------------------------------------------------------
# Gross ceiling: down-only clamp on target and projected books
# ---------------------------------------------------------------------------


def test_overlevered_vol_target_is_clamped_exactly_to_the_ceiling() -> None:
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"A": 1.0}),
            SleeveSpec("high", 0.5, {"B": 1.0}),
        ],
        ledger=StagedLedger(
            covariances=[_diagonal_covariance({"low": 0.03, "high": 0.03})]
        ),
        book_vol_target=0.09,
        gross_cap=1.0,
    )

    result = harness.run()

    # Vol-targeting alone wants gross ~4.24; the clamp lands it on the cap.
    assert signed_order_weights(result) == {
        "A": pytest.approx(0.5),
        "B": pytest.approx(0.5),
    }


def test_underlevered_book_is_not_scaled_up_to_the_cap() -> None:
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"A": 1.0}),
            SleeveSpec("high", 0.5, {"B": 1.0}),
        ],
        ledger=StagedLedger(
            covariances=[_diagonal_covariance({"low": 0.40, "high": 0.40})]
        ),
        book_vol_target=0.09,
        gross_cap=1.0,
    )

    result = harness.run()

    assert signed_order_weights(result) == {
        "A": pytest.approx(0.15909902576697319, abs=1e-6),
        "B": pytest.approx(0.15909902576697319, abs=1e-6),
    }


def test_clamp_preserves_relative_weights() -> None:
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"A": 1.0}),
            SleeveSpec("high", 0.5, {"B": 0.5}),
        ],
        ledger=StagedLedger(
            covariances=[_diagonal_covariance({"low": 0.03, "high": 0.03})]
        ),
        book_vol_target=0.09,
        gross_cap=1.0,
    )

    weights = signed_order_weights(harness.run())

    assert weights == {
        "A": pytest.approx(2.0 / 3.0, abs=1e-6),
        "B": pytest.approx(1.0 / 3.0, abs=1e-6),
    }


def test_clamp_composes_with_drawdown_delever() -> None:
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"A": 1.0}),
            SleeveSpec("high", 0.5, {"B": 1.0}),
        ],
        ledger=StagedLedger(
            covariances=[_diagonal_covariance({"low": 0.03, "high": 0.03})],
            drawdown=0.25,
        ),
        book_vol_target=0.09,
        gross_cap=1.0,
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05, end_drawdown=0.25, floor_multiplier=0.5
        ),
    )

    result = harness.run()

    # De-lever halves the solve (~4.24 -> ~2.12 gross); the clamp still binds.
    assert signed_order_weights(result) == {
        "A": pytest.approx(0.5),
        "B": pytest.approx(0.5),
    }


def test_drawdown_delever_keeps_gross_within_the_ceiling() -> None:
    harness = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.5})],
        ledger=StagedLedger(drawdown=0.25),
        gross_cap=0.20,
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05, end_drawdown=0.25, floor_multiplier=0.5
        ),
    )

    result = harness.run()

    # Floor multiplier 0.5 puts the target at 0.25; the clamp lands it on 0.20.
    assert signed_order_weights(result) == {"AAA": pytest.approx(0.20)}


def test_within_band_drift_over_the_ceiling_is_clamped_not_failed() -> None:
    result = build_harness(
        [
            SleeveSpec(
                "trend",
                1.0,
                {"AAA": 0.5, "BBB": 0.5},
                bands={
                    "AAA": DriftBand.symmetric(0.05),
                    "BBB": DriftBand.symmetric(0.05),
                },
            )
        ],
        realized={"AAA": 0.53, "BBB": 0.53},
        gross_cap=1.0,
    ).run()

    # Both drifts are within band, but the projected book (1.06 gross) exceeds
    # the ceiling: the authoritative clamp re-derives corrective sells.
    assert signed_order_weights(result) == {
        "AAA": pytest.approx(-0.03),
        "BBB": pytest.approx(-0.03),
    }
    assert result.summary.gate_outcome == GateOutcome.PASS


# ---------------------------------------------------------------------------
# Aggregate drift: book-level fidelity trip
# ---------------------------------------------------------------------------


def test_aggregate_drift_within_threshold_holds_the_book() -> None:
    result = build_harness(
        [
            SleeveSpec(
                "trend",
                1.0,
                {"AAA": 0.50, "BBB": 0.30},
                bands={
                    "AAA": DriftBand.symmetric(0.10),
                    "BBB": DriftBand.symmetric(0.10),
                },
            )
        ],
        realized={"AAA": 0.52, "BBB": 0.28},
        aggregate_drift_threshold=0.05,
    ).run()

    assert result.orders == ()


def test_aggregate_drift_trip_forces_a_full_cleanup() -> None:
    result = build_harness(
        [
            SleeveSpec(
                "trend",
                1.0,
                {"AAA": 0.50, "BBB": 0.30},
                bands={
                    "AAA": DriftBand.symmetric(0.10),
                    "BBB": DriftBand.symmetric(0.10),
                },
            )
        ],
        realized={"AAA": 0.52, "BBB": 0.28},
        aggregate_drift_threshold=0.03,
    ).run()

    # Drift 0.04 > 0.03: bands are ignored, every name trades back to target.
    assert signed_order_weights(result) == {
        "AAA": pytest.approx(-0.02),
        "BBB": pytest.approx(0.02),
    }


def test_many_small_drifts_trip_the_aggregate_threshold() -> None:
    result = build_harness(
        [
            SleeveSpec(
                "trend",
                1.0,
                {"AAA": 0.20, "BBB": 0.20, "CCC": 0.20, "DDD": 0.20},
                bands={
                    symbol: DriftBand.symmetric(0.02)
                    for symbol in ("AAA", "BBB", "CCC", "DDD")
                },
            )
        ],
        realized={"AAA": 0.21, "BBB": 0.21, "CCC": 0.21, "DDD": 0.21},
        per_name_cap=0.25,
        aggregate_drift_threshold=0.03,
    ).run()

    assert signed_order_weights(result) == {
        symbol: pytest.approx(-0.01) for symbol in ("AAA", "BBB", "CCC", "DDD")
    }


def test_cleanup_stays_subordinate_to_the_gross_ceiling() -> None:
    result = build_harness(
        [
            SleeveSpec(
                "trend",
                1.0,
                {"AAA": 0.40, "BBB": 0.30},
                bands={
                    "AAA": DriftBand.symmetric(0.10),
                    "BBB": DriftBand.symmetric(0.10),
                },
            )
        ],
        realized={"AAA": 0.36, "BBB": 0.26},
        aggregate_drift_threshold=0.03,
        gross_cap=0.50,
    ).run()

    # Cleanup targets gross 0.70; the down-only clamp pulls the projected book
    # to the 0.50 ceiling (5/7 of each target: 0.285714 and 0.214286).
    assert signed_order_weights(result) == {
        "AAA": pytest.approx(-0.074286),
        "BBB": pytest.approx(-0.045714),
    }

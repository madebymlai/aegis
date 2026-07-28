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
from aegis_trader.trader.pipeline import GateOutcome, HaltCause
from tests.support.rebalance_harness import (
    SleeveSpec,
    StagedLedger,
    WeightSleeveBundle,
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
    assert result.halt_cause == HaltCause.PER_NAME_CAP_BREACH
    assert result.halt_reason is not None
    assert "AAA.TEST" in result.halt_reason


def test_net_cap_breach_returns_no_orders_and_halts() -> None:
    harness = build_harness(
        [SleeveSpec("trend", 1.0, {"AAA": 0.15, "BBB": -0.01})],
        net_cap=0.10,
    )

    result = harness.run()

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_cause == HaltCause.NET_CAP_BREACH
    assert result.halt_reason is not None


def test_planning_failure_halts_with_the_catch_all_cause() -> None:
    """Any other planning ValueError (here: a degenerate staged variance the
    allocator rejects) halts with PLANNING_FAILED, never a silent pass."""
    low = SleeveName("low")
    degenerate = {low: {low: 0.0}}
    harness = build_harness(
        [SleeveSpec("low", 1.0, {"LOW": 1.0})],
        ledger=StagedLedger(covariances=[degenerate]),
    )

    result = harness.run()

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_cause == HaltCause.PLANNING_FAILED
    assert result.halt_reason is not None


def test_passing_rebalance_carries_no_halt_cause() -> None:
    result = build_harness([SleeveSpec("trend", 1.0, {"AAA": 0.5})]).run()

    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.halt_cause is None


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


def test_uncorrelated_sleeves_keep_the_zero_correlation_scale() -> None:
    low, high = SleeveName("low"), SleeveName("high")
    uncorrelated = {
        low: {low: 0.01, high: 0.0},
        high: {low: 0.0, high: 0.01},
    }
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"LOW": 1.0}),
            SleeveSpec("high", 0.5, {"HIGH": 1.0}),
        ],
        ledger=StagedLedger(covariances=[uncorrelated]),
        book_vol_target=0.05,
    )

    result = harness.run()

    assert signed_order_weights(result) == {
        "LOW": pytest.approx(0.353553, abs=1e-6),
        "HIGH": pytest.approx(0.353553, abs=1e-6),
    }


def test_correlated_sleeves_are_scaled_down_harder_than_uncorrelated() -> None:
    low, high = SleeveName("low"), SleeveName("high")
    correlated = {
        low: {low: 0.01, high: 0.009},
        high: {low: 0.009, high: 0.01},
    }
    harness = build_harness(
        [
            SleeveSpec("low", 0.5, {"LOW": 1.0}),
            SleeveSpec("high", 0.5, {"HIGH": 1.0}),
        ],
        ledger=StagedLedger(covariances=[correlated]),
        book_vol_target=0.05,
    )

    result = harness.run()

    # Correlation 0.9 raises book vol, so each sleeve lands below the 0.353553
    # the identical uncorrelated staging yields (see the test above).
    assert signed_order_weights(result) == {
        "LOW": pytest.approx(0.256495, abs=1e-6),
        "HIGH": pytest.approx(0.256495, abs=1e-6),
    }


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


# ---------------------------------------------------------------------------
# The live drawdown governor (book.toml), driven synthetically.
#
# The armed calibration is dormant across the whole validated window by design:
# measured maxDD is -10.2% at gross 1.75 over 2018-2024 including COVID and 2022
# (runs/aegis/2026-07-05, B1/GH #79), and the ramp starts at -15%. No backtest
# therefore exercises it, so a synthetic drawdown is the only coverage it gets.

_LIVE_GOVERNOR = DrawdownDeleverCurve(
    start_drawdown=0.15, end_drawdown=0.30, floor_multiplier=0.40
)
_MEASURED_MAX_DRAWDOWN = 0.102
# The harness sizes each order to a whole micro-NAV unit, so a summed gross of
# two instruments carries a couple of those units of rounding.
_MICRO_NAV = 1e-6


def _live_governor_gross(drawdown: float) -> float:
    """Netted book gross under the live governor at one drawdown depth.

    Sleeve vols are high enough that the vol-target solve lands far below
    ``gross_cap``, so the clamp never binds and the governor's cut shows through
    instead of being absorbed by the ceiling.
    """
    harness = build_harness(
        [
            SleeveSpec("alpha", 0.5, {"AAA": 1.0}),
            SleeveSpec("beta", 0.5, {"BBB": 1.0}),
        ],
        ledger=StagedLedger(
            covariances=[_diagonal_covariance({"alpha": 0.30, "beta": 0.30})],
            drawdown=drawdown,
        ),
        book_vol_target=0.09,
        gross_cap=1.75,
        drawdown_delever=_LIVE_GOVERNOR,
    )
    return sum(abs(weight) for weight in signed_order_weights(harness.run()).values())


@pytest.mark.parametrize(
    ("drawdown", "expected_multiplier"),
    [
        (0.0, 1.0),
        (_MEASURED_MAX_DRAWDOWN, 1.0),
        (0.15, 1.0),
        (0.18, 0.88),
        (0.20, 0.80),
        (0.25, 0.60),
        (0.30, 0.40),
        (0.45, 0.40),
    ],
)
def test_live_drawdown_governor_scales_the_book_along_its_ramp(
    drawdown: float, expected_multiplier: float
) -> None:
    """Exposure tracks the ramp: flat to -15%, linear to the floor at -30%, then
    pinned. Asserted as a ratio to the undelevered book so this covers the
    governor's response, not the vol-target arithmetic other tests already pin."""
    undelevered = _live_governor_gross(0.0)

    assert _live_governor_gross(drawdown) == pytest.approx(
        undelevered * expected_multiplier, abs=2 * _MICRO_NAV
    )


def test_live_drawdown_governor_is_dormant_through_the_measured_envelope() -> None:
    """Calibration invariant: the governor must not fire on a drawdown the book
    has actually produced. De-levering inside the validated range is *measured* to
    cost 4.1-4.8pp at book level (runs/aegis/2026-07-05 finding 2 — the 2020 gain
    was the governor NOT firing), so the ramp starts above measured maxDD with
    headroom. Re-tuning ``start_drawdown`` below -10.2% breaks this."""
    assert _LIVE_GOVERNOR.multiplier_for(_MEASURED_MAX_DRAWDOWN) == 1.0
    assert _live_governor_gross(_MEASURED_MAX_DRAWDOWN) == pytest.approx(
        _live_governor_gross(0.0)
    )


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
                    "AAA": DriftBand.symmetric(0.02),
                    "BBB": DriftBand.symmetric(0.02),
                    "CCC": DriftBand.symmetric(0.02),
                    "DDD": DriftBand.symmetric(0.02),
                },
            )
        ],
        realized={"AAA": 0.21, "BBB": 0.21, "CCC": 0.21, "DDD": 0.21},
        per_name_cap=0.25,
        aggregate_drift_threshold=0.03,
    ).run()

    assert signed_order_weights(result) == {
        "AAA": pytest.approx(-0.01),
        "BBB": pytest.approx(-0.01),
        "CCC": pytest.approx(-0.01),
        "DDD": pytest.approx(-0.01),
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


# ---------------------------------------------------------------------------
# Retained targets for independently due Sleeves (aegis-rd-9qkr.2)
# ---------------------------------------------------------------------------


class _ExplodesWhenComputedBundle(WeightSleeveBundle):
    """A sleeve bundle that raises on every compute — due-invocation probe."""

    def compute_weights(self, native_prices, *, currency_conversion=None):
        raise RuntimeError("component exploded")


class _ExplodesOnSecondComputeBundle(WeightSleeveBundle):
    """A sleeve bundle whose first compute succeeds and later computes raise."""

    def compute_weights(self, native_prices, *, currency_conversion=None):
        calls = getattr(self, "_calls", 0) + 1
        object.__setattr__(self, "_calls", calls)
        if calls > 1:
            raise RuntimeError("component exploded")
        return super().compute_weights(
            native_prices, currency_conversion=currency_conversion
        )


def test_rebalance_allocates_the_full_retained_book_when_one_sleeve_is_due() -> None:
    harness = build_harness(
        [
            SleeveSpec("fast", 0.5, {"AAA": 0.4}),
            SleeveSpec("slow", 0.5, {"BBB": 0.2}),
        ]
    )
    harness.run()

    result = harness.run(due=["fast"])

    assert result.summary.num_sleeves == 2
    assert set(harness.pipeline.last_sleeve_weights) == {
        SleeveName("fast"),
        SleeveName("slow"),
    }


def test_re_net_with_unchanged_targets_emits_no_orders_for_non_due_sleeves() -> None:
    # Grilling amendment (aegis-rd-9qkr.2): a due update whose recomputed
    # targets are unchanged, with no risk-control trip, must be a no-op for
    # instruments owned by non-due Sleeves.
    harness = build_harness(
        [
            SleeveSpec("fast", 0.5, {"AAA": 0.4}),
            SleeveSpec("slow", 0.5, {"BBB": 0.2}),
        ],
        realized={"AAA": 0.2, "BBB": 0.1},
    )
    harness.run()

    result = harness.run(due=["fast"])

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.PASS


def test_non_due_sleeve_is_not_invoked() -> None:
    poison = SleeveSpec("poison", 0.5, {"BBB": 0.2})
    harness = build_harness(
        [SleeveSpec("fast", 0.5, {"AAA": 0.4}), poison],
        bundle_overrides={"poison.whl": _ExplodesWhenComputedBundle(poison)},
    )
    first = harness.run()

    second = harness.run(due=["fast"])

    assert [failure.sleeve for failure in first.sleeve_failures] == [
        SleeveName("poison")
    ]
    assert second.sleeve_failures == ()


def test_failed_due_sleeve_retains_its_prior_valid_target() -> None:
    fragile = SleeveSpec("fragile", 0.5, {"BBB": 0.2})
    harness = build_harness(
        [SleeveSpec("fast", 0.5, {"AAA": 0.4}), fragile],
        bundle_overrides={"fragile.whl": _ExplodesOnSecondComputeBundle(fragile)},
    )
    first = harness.run()

    second = harness.run()

    assert first.sleeve_failures == ()
    assert [failure.sleeve for failure in second.sleeve_failures] == [
        SleeveName("fragile")
    ]
    assert signed_order_weights(second) == {
        "AAA": pytest.approx(0.20),
        "BBB": pytest.approx(0.10),
    }

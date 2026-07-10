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
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.trader.pipeline import GateOutcome
from tests.support.rebalance_harness import (
    SequencedCovarianceLedger,
    SleeveSpec,
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
        ledger=SequencedCovarianceLedger([flat, shifted]),
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

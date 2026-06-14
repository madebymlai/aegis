"""Unit tests for the pure-domain rebalancer — zero Nautilus."""

import pandas as pd
import pytest

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.types import Figi, OrderIntent, OrderSide, SleeveName


def make_book(sleeves: list[tuple[str, str, float]]) -> BookConfig:
    return BookConfig(
        sleeves=tuple(
            SleeveConfig(name=SleeveName(n), wheel_filename=w, budget=b)
            for n, w, b in sleeves
        )
    )


class TestRebalanceSingleSleeve:
    """Tracer slice: one sleeve, simple weight→OrderIntent, no bands/gates."""

    @staticmethod
    def _call(target: pd.DataFrame, nav: float, book: BookConfig) -> list[OrderIntent]:
        """Helper: wrap single-sleeve target in the multi-sleeve dict form."""
        return rebalance({book.sleeves[0].name: target}, nav, book)

    def test_single_figi_buy(self):
        """A positive target weight → BUY for that NAV fraction."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [0.5]},  # FIGI for VUSA.L
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert len(orders) == 1
        o = orders[0]
        assert o.figi == Figi("BBG000B9XRY4")
        assert o.side == OrderSide.BUY
        assert o.quantity == pytest.approx(50_000.0)

    def test_single_figi_sell(self):
        """A negative target weight → SELL for that NAV fraction."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [-0.3]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert len(orders) == 1
        o = orders[0]
        assert o.side == OrderSide.SELL
        assert o.quantity == pytest.approx(30_000.0)

    def test_budget_scales_quantity(self):
        """A sleeve budget < 1.0 scales the order quantity proportionally."""
        book = make_book([("trend", "trend_lse-abc123.whl", 0.5)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [0.5]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert orders[0].quantity == pytest.approx(25_000.0)

    def test_zero_weight_yields_no_order(self):
        """A zero-weight instrument produces no OrderIntent."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [0.0]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert len(orders) == 0

    def test_near_zero_weight_filtered(self):
        """Weights below 1e-12 produce no order (float noise guard)."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [1e-13]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert len(orders) == 0

    def test_multiple_figis(self):
        """Multiple FIGIs each get their own OrderIntent."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"FIGI_A": [0.4], "FIGI_B": [-0.2]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert len(orders) == 2
        orders_by_figi = {o.figi.value: o for o in orders}
        assert orders_by_figi["FIGI_A"].side == OrderSide.BUY
        assert orders_by_figi["FIGI_A"].quantity == pytest.approx(40_000.0)
        assert orders_by_figi["FIGI_B"].side == OrderSide.SELL
        assert orders_by_figi["FIGI_B"].quantity == pytest.approx(20_000.0)

    def test_uses_latest_row(self):
        """Only the last row of the target frame is used."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"FIGI_A": [0.1, 0.2, 0.5]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(50_000.0)

    def test_empty_target_returns_empty(self):
        """An empty target DataFrame produces no orders."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"FIGI_A": pd.Series([], dtype=float)},
            index=pd.DatetimeIndex([], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = self._call(target, nav, book)

        assert orders == []


class TestRebalanceMultiSleeve:
    """Slice 2: multi-sleeve netting + budget scaling."""

    @staticmethod
    def _target(figi_to_weight: dict[str, float]) -> pd.DataFrame:
        """Build a one-row target-weight DataFrame."""
        df = pd.DataFrame(
            {k: [v] for k, v in figi_to_weight.items()},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        df.columns.name = "figi"
        return df

    # ── overlap ──────────────────────────────────────────────────────────

    def test_overlapping_sleeves_net(self):
        """Two sleeves sharing a FIGI net to one OrderIntent for the residual."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.6),
            ("carry", "carry-def.whl", 0.4),
        ])
        trend_target = self._target({"FIGI_A": 0.5})   # budget=0.6 → scaled=0.30
        carry_target = self._target({"FIGI_A": -0.2})   # budget=0.4 → scaled=-0.08
        # net = 0.30 - 0.08 = 0.22 → BUY, qty=0.22*100000=22000

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 1
        o = orders[0]
        assert o.figi == Figi("FIGI_A")
        assert o.side == OrderSide.BUY
        assert o.quantity == pytest.approx(22_000.0)

    def test_overlap_cancels_to_zero(self):
        """Equal and opposite scaled weights → no order (zero net)."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.5),
            ("carry", "carry-def.whl", 0.5),
        ])
        trend_target = self._target({"FIGI_A": 0.4})   # scaled=0.20
        carry_target = self._target({"FIGI_A": -0.4})   # scaled=-0.20
        # net = 0.0

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 0

    def test_overlap_both_positive_sum(self):
        """Two sleeves long the same FIGI → additive net."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.6),
            ("carry", "carry-def.whl", 0.4),
        ])
        trend_target = self._target({"FIGI_A": 0.5})   # scaled=0.30
        carry_target = self._target({"FIGI_A": 0.25})   # scaled=0.10
        # net = 0.40 → BUY, qty=40_000

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 1
        o = orders[0]
        assert o.side == OrderSide.BUY
        assert o.quantity == pytest.approx(40_000.0)

    # ── disjoint ─────────────────────────────────────────────────────────

    def test_disjoint_sleeves_concatenate(self):
        """Two sleeves with completely different FIGIs."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.6),
            ("carry", "carry-def.whl", 0.4),
        ])
        trend_target = self._target({"FIGI_A": 0.5})   # scaled=0.30
        carry_target = self._target({"FIGI_B": -0.3})   # scaled=-0.12

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 2
        by_figi = {o.figi.value: o for o in orders}
        assert by_figi["FIGI_A"].side == OrderSide.BUY
        assert by_figi["FIGI_A"].quantity == pytest.approx(30_000.0)
        assert by_figi["FIGI_B"].side == OrderSide.SELL
        assert by_figi["FIGI_B"].quantity == pytest.approx(12_000.0)

    # ── mixed ────────────────────────────────────────────────────────────

    def test_mixed_overlap_and_disjoint(self):
        """Overlapping FIGI nets; disjoint FIGI stands alone."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.5),
            ("carry", "carry-def.whl", 0.5),
        ])
        trend_target = self._target({"FIGI_A": 0.4, "FIGI_C": 0.3})
        carry_target = self._target({"FIGI_A": -0.1, "FIGI_B": 0.2})
        # FIGI_A: 0.5*0.4 + 0.5*(-0.1) = 0.20 - 0.05 = 0.15 → BUY 15_000
        # FIGI_B: 0.5*0.2 = 0.10 → BUY 10_000
        # FIGI_C: 0.5*0.3 = 0.15 → BUY 15_000

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 3
        by_figi = {o.figi.value: o for o in orders}
        assert by_figi["FIGI_A"].quantity == pytest.approx(15_000.0)
        assert by_figi["FIGI_B"].quantity == pytest.approx(10_000.0)
        assert by_figi["FIGI_C"].quantity == pytest.approx(15_000.0)
        for o in orders:
            assert o.side == OrderSide.BUY

    # ── budget scaling ───────────────────────────────────────────────────

    def test_budget_scales_before_netting(self):
        """A sleeve with budget=0 contributes nothing to the net."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.6),
            ("carry", "carry-def.whl", 0.0),  # zero budget
        ])
        trend_target = self._target({"FIGI_A": 0.5})
        carry_target = self._target({"FIGI_A": 0.8})

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        # carry budget is 0, so only trend contributes: 0.6*0.5 = 0.30 → 30_000
        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(30_000.0)

    def test_all_budgets_sum_less_than_one(self):
        """Gross budget < 1.0 → all quantities scaled below NAV."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.3),
            ("carry", "carry-def.whl", 0.2),
        ])
        trend_target = self._target({"FIGI_A": 0.5})
        carry_target = self._target({"FIGI_B": 0.5})
        # FIGI_A: 0.3*0.5 = 0.15 → 15_000
        # FIGI_B: 0.2*0.5 = 0.10 → 10_000

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        by_figi = {o.figi.value: o for o in orders}
        assert by_figi["FIGI_A"].quantity == pytest.approx(15_000.0)
        assert by_figi["FIGI_B"].quantity == pytest.approx(10_000.0)

    # ── edge cases ───────────────────────────────────────────────────────

    def test_three_sleeves_complex_netting(self):
        """Three sleeves, overlapping on some FIGIs."""
        book = make_book([
            ("a", "a.whl", 0.4),
            ("b", "b.whl", 0.3),
            ("c", "c.whl", 0.3),
        ])
        a_target = self._target({"X": 0.5, "Y": -0.2})
        b_target = self._target({"X": -0.3, "Z": 0.4})
        c_target = self._target({"Y": 0.3, "Z": -0.1})
        # X: 0.4*0.5 + 0.3*(-0.3) + 0.3*0.0 = 0.20 - 0.09 = 0.11 → BUY 11_000
        # Y: 0.4*(-0.2) + 0.3*0.0 + 0.3*0.3 = -0.08 + 0.09 = 0.01 → BUY 1_000
        # Z: 0.4*0.0 + 0.3*0.4 + 0.3*(-0.1) = 0.12 - 0.03 = 0.09 → BUY 9_000

        orders = rebalance(
            {book.sleeves[0].name: a_target,
             book.sleeves[1].name: b_target,
             book.sleeves[2].name: c_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 3
        by_figi = {o.figi.value: o for o in orders}
        assert by_figi["X"].quantity == pytest.approx(11_000.0)
        assert by_figi["X"].side == OrderSide.BUY
        assert by_figi["Y"].quantity == pytest.approx(1_000.0)
        assert by_figi["Y"].side == OrderSide.BUY
        assert by_figi["Z"].quantity == pytest.approx(9_000.0)
        assert by_figi["Z"].side == OrderSide.BUY

    def test_nav_zero_raises(self):
        """Non-positive NAV raises ValueError."""
        book = make_book([
            ("a", "a.whl", 0.5),
            ("b", "b.whl", 0.5),
        ])
        a_target = self._target({"FIGI_A": 0.4})
        b_target = self._target({"FIGI_A": -0.1})

        with pytest.raises(ValueError, match="NAV"):
            rebalance(
                {book.sleeves[0].name: a_target, book.sleeves[1].name: b_target},
                nav=0.0,
                book=book,
            )

    def test_sleeve_missing_from_targets_skipped(self):
        """A sleeve with no target data is silently skipped."""
        book = make_book([
            ("trend", "trend.whl", 0.5),
            ("carry", "carry.whl", 0.5),
        ])
        trend_target = self._target({"FIGI_A": 0.4})
        # carry has no target → skipped

        orders = rebalance(
            {book.sleeves[0].name: trend_target},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 1
        # Only trend contributes: 0.5*0.4 = 0.20 → 20_000
        assert orders[0].quantity == pytest.approx(20_000.0)

    def test_sleeve_empty_target_skipped(self):
        """A sleeve with an empty DataFrame is silently skipped."""
        book = make_book([
            ("trend", "trend.whl", 0.5),
            ("carry", "carry.whl", 0.5),
        ])
        trend_target = self._target({"FIGI_A": 0.4})
        empty = pd.DataFrame(
            {"FIGI_B": pd.Series([], dtype=float)},
            index=pd.DatetimeIndex([], name="timestamp"),
        )
        empty.columns.name = "figi"

        orders = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: empty},
            nav=100_000.0,
            book=book,
        )

        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(20_000.0)


class TestRebalanceSlice4:
    """Slice 4: realised-book gate, asymmetric bands, caps, aggregate drift."""

    @staticmethod
    def _target(figi_to_weight: dict[str, float]) -> pd.DataFrame:
        """Build a one-row target-weight DataFrame."""
        df = pd.DataFrame(
            {k: [v] for k, v in figi_to_weight.items()},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        df.columns.name = "figi"
        return df

    @staticmethod
    def _book(name: str = "trend", budget: float = 1.0, **kwargs) -> BookConfig:
        """Single-sleeve book helper."""
        return BookConfig(
            sleeves=(SleeveConfig(name=SleeveName(name), wheel_filename=f"{name}.whl", budget=budget),),
            **kwargs,
        )

    # ── band gate ───────────────────────────────────────────────────────

    def test_band_gate_suppresses_small_drift(self):
        """Realised position within symmetric band → no order."""
        book = self._book(default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.50})

        # Realised = 0.51 → delta = -0.01, within band (0.02) → no trade
        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.51},
        )
        assert orders == []

    def test_band_gate_trades_when_outside_band(self):
        """Realised position outside band → corrective order."""
        book = self._book(default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.50})

        # Realised = 0.55 → delta = -0.05, outside band (0.02) → SELL 5_000
        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.55},
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        assert orders[0].quantity == pytest.approx(5_000.0)

    def test_asymmetric_band_tail(self):
        """Asymmetric bands: tight up trims spike; loose down tolerates dip."""
        book = self._book(
            default_band_up=0.02, default_band_down=0.02,
            band_overrides=(("FIGI_TAIL", 0.01, 0.05),),
        )
        target = self._target({"FIGI_TAIL": 0.50})

        # Spike: realised = 0.52 → delta = -0.02 > band_up=0.01 → trigger SELL
        orders_up = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_TAIL": 0.52},
        )
        assert len(orders_up) == 1
        assert orders_up[0].side == OrderSide.SELL

        # Dip: realised = 0.48 → delta = +0.02 < band_down=0.05 → suppressed
        orders_down = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_TAIL": 0.48},
        )
        assert orders_down == []

    def test_band_only_applied_when_realized_present(self):
        """Without realised data, band is not applied and full target is traded."""
        book = self._book(default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.01})  # tiny target within band

        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights=None,
        )
        # No realised data → band not applied → trade the full target
        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(1_000.0)

    # ── cap gate — per-name ─────────────────────────────────────────────

    def test_per_name_cap_breach_band_creates_corrective_verified(self):
        """Band gate creates corrective trade for cap breach; cap gate verifies post_book."""
        book = self._book(per_name_cap=0.10, default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.08})

        # Realised = 0.12 → exceeds per_name_cap 0.10.
        # Band: delta = 0.08 - 0.12 = -0.04 > band_up=0.02 → SELL.
        # Cap gate: realised breach; already correcting → verify post_book=0.08 ≤ cap.
        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.12},
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        # delta = -0.04 → SELL 4_000
        assert orders[0].quantity == pytest.approx(4_000.0)

    def test_per_name_cap_breach_band_suppressed_corrective_order(self):
        """Realised breaches per_name_cap but band suppresses trade → widen."""
        # Use wide bands so the band gate doesn't trigger on its own.
        book = self._book(per_name_cap=0.10, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": 0.08})

        # Realised = 0.12 → breaches per_name_cap 0.10.
        # Band: delta = 0.08 - 0.12 = -0.04, within band (0.10) → suppressed
        # But cap gate sees the breach and widens → corrective SELL to cap
        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.12},
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        # Realised 0.12 → cap 0.10 → sell 0.02 * 100_000 = 2_000
        assert orders[0].quantity == pytest.approx(2_000.0)

    def test_per_name_cap_breach_unfixable_fails_closed(self):
        """Target itself exceeds per_name_cap → fail closed (unfixable)."""
        book = self._book(per_name_cap=0.10, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": 0.15})  # target > cap

        # Realised = 0.15 (at target). Band: delta=0 → suppressed.
        # Cap check: realised 0.15 > cap 0.10, and target 0.15 > cap 0.10 → unfixable
        with pytest.raises(ValueError, match="unfixable"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={"FIGI_A": 0.15},
            )

    def test_per_name_cap_breach_short_position(self):
        """Negative realised weight exceeding per_name_cap triggers widen."""
        book = self._book(per_name_cap=0.10, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": -0.08})

        # Realised = -0.12 → breaches per_name_cap (-0.10) on short side
        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": -0.12},
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.BUY
        # widen-to-compliance: cap_w = -per_name_cap = -0.10
        # delta = -0.10 - (-0.12) = +0.02 → BUY 2_000
        assert orders[0].quantity == pytest.approx(2_000.0)

    # ── gross / net caps ────────────────────────────────────────────────

    def test_gross_cap_breach_fails_closed(self):
        """Post-execution gross exceeds cap → fail closed."""
        book = self._book(gross_cap=0.50)
        target = self._target({"FIGI_A": 0.30, "FIGI_B": 0.30})

        with pytest.raises(ValueError, match="Gross exposure"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
            )

    def test_net_cap_breach_fails_closed(self):
        """Post-execution net exceeds cap → fail closed."""
        book = self._book(net_cap=0.10)
        target = self._target({"FIGI_A": 0.15, "FIGI_B": -0.01})

        with pytest.raises(ValueError, match="Net exposure"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
            )

    # ── aggregate drift ─────────────────────────────────────────────────

    def test_aggregate_drift_within_threshold_no_error(self):
        """Aggregate drift below threshold → no error."""
        book = self._book(aggregate_drift_threshold=0.05, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": 0.50, "FIGI_B": 0.30})

        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.52, "FIGI_B": 0.28},
        )
        # Drift = |0.50-0.52| + |0.30-0.28| = 0.02 + 0.02 = 0.04 < 0.05 → OK
        # But bands are wide so no orders
        assert orders == []

    def test_aggregate_drift_exceeds_threshold_fails_closed(self):
        """Aggregate drift above threshold → fail closed."""
        book = self._book(aggregate_drift_threshold=0.03, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": 0.50, "FIGI_B": 0.30})

        with pytest.raises(ValueError, match="Aggregate drift"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={"FIGI_A": 0.52, "FIGI_B": 0.28},
            )

    # ── N·band correlated-drift ─────────────────────────────────────────

    def test_correlated_drift_caught_by_caps(self):
        """When all instruments drift together but stay within individual
        bands and per-name caps, aggregate drift catches the cumulative effect."""
        book = self._book(
            per_name_cap=0.25,
            aggregate_drift_threshold=0.03,
            default_band_up=0.02,
            default_band_down=0.02,
        )
        target = self._target({
            "FIGI_A": 0.20, "FIGI_B": 0.20, "FIGI_C": 0.20, "FIGI_D": 0.20,
        })
        # Each drifts +1% (within band) but aggregate drift = 4×1% = 4% > 3%
        # Per-name: all ≤ 0.21 < 0.25 (OK)
        # No gross cap → aggregate drift fires

        with pytest.raises(ValueError, match="Aggregate drift"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={
                    "FIGI_A": 0.21, "FIGI_B": 0.21,
                    "FIGI_C": 0.21, "FIGI_D": 0.21,
                },
            )

    def test_cap_gate_sees_realized_not_target(self):
        """The gate checks the REALIZED book, not just the all-at-target book.
        A realized position at cap should be flagged even if target is safe."""
        book = self._book(
            per_name_cap=0.10,
            default_band_up=0.10,  # wide band to suppress band gate
            default_band_down=0.10,
        )
        target = self._target({"FIGI_A": 0.08})  # target within cap

        # Realised = 0.12 → breaches per_name_cap, but band hides it
        # The cap gate must catch this regardless
        orders = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.12},
        )
        # Widen-to-compliance: sell down to cap=0.10
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        assert orders[0].quantity == pytest.approx(2_000.0)  # (0.12-0.10)*100k

"""Unit tests for the pure-domain rebalancer — zero Nautilus."""

import pandas as pd
import pytest

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.types import Figi, OrderIntent, OrderSide, RebalanceResult, SleeveName


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
    def _call(target: pd.DataFrame, nav: float, book: BookConfig) -> RebalanceResult:
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

        result = self._call(target, nav, book)

        assert len(result.orders) == 1
        o = result.orders[0]
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

        result = self._call(target, nav, book)

        assert len(result.orders) == 1
        o = result.orders[0]
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

        result = self._call(target, nav, book)

        assert result.orders[0].quantity == pytest.approx(25_000.0)

    def test_zero_weight_yields_no_order(self):
        """A zero-weight instrument produces no OrderIntent."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [0.0]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        result = self._call(target, nav, book)

        assert len(result.orders) == 0

    def test_near_zero_weight_filtered(self):
        """Weights below 1e-12 produce no order (float noise guard)."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [1e-13]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        result = self._call(target, nav, book)

        assert len(result.orders) == 0

    def test_multiple_figis(self):
        """Multiple FIGIs each get their own OrderIntent."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"FIGI_A": [0.4], "FIGI_B": [-0.2]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        result = self._call(target, nav, book)

        assert len(result.orders) == 2
        orders_by_figi = {o.figi.value: o for o in result.orders}
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

        result = self._call(target, nav, book)

        assert len(result.orders) == 1
        assert result.orders[0].quantity == pytest.approx(50_000.0)

    def test_empty_target_returns_empty(self):
        """An empty target DataFrame produces no orders."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"FIGI_A": pd.Series([], dtype=float)},
            index=pd.DatetimeIndex([], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        result = self._call(target, nav, book)

        assert result.orders == ()


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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 1
        o = result.orders[0]
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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 0

    def test_overlap_both_positive_sum(self):
        """Two sleeves long the same FIGI → additive net."""
        book = make_book([
            ("trend", "trend-abc.whl", 0.6),
            ("carry", "carry-def.whl", 0.4),
        ])
        trend_target = self._target({"FIGI_A": 0.5})   # scaled=0.30
        carry_target = self._target({"FIGI_A": 0.25})   # scaled=0.10
        # net = 0.40 → BUY, qty=40_000

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 1
        o = result.orders[0]
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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 2
        by_figi = {o.figi.value: o for o in result.orders}
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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 3
        by_figi = {o.figi.value: o for o in result.orders}
        assert by_figi["FIGI_A"].quantity == pytest.approx(15_000.0)
        assert by_figi["FIGI_B"].quantity == pytest.approx(10_000.0)
        assert by_figi["FIGI_C"].quantity == pytest.approx(15_000.0)
        for o in result.orders:
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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        # carry budget is 0, so only trend contributes: 0.6*0.5 = 0.30 → 30_000
        assert len(result.orders) == 1
        assert result.orders[0].quantity == pytest.approx(30_000.0)

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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
        )

        by_figi = {o.figi.value: o for o in result.orders}
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

        result = rebalance(
            {book.sleeves[0].name: a_target,
             book.sleeves[1].name: b_target,
             book.sleeves[2].name: c_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 3
        by_figi = {o.figi.value: o for o in result.orders}
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

        result = rebalance(
            {book.sleeves[0].name: trend_target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 1
        # Only trend contributes: 0.5*0.4 = 0.20 → 20_000
        assert result.orders[0].quantity == pytest.approx(20_000.0)

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

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: empty},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 1
        assert result.orders[0].quantity == pytest.approx(20_000.0)

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
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.51},
        )
        assert result.orders == ()

    def test_band_gate_trades_when_outside_band(self):
        """Realised position outside band → corrective order."""
        book = self._book(default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.50})

        # Realised = 0.55 → delta = -0.05, outside band (0.02) → SELL 5_000
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.55},
        )
        assert len(result.orders) == 1
        assert result.orders[0].side == OrderSide.SELL
        assert result.orders[0].quantity == pytest.approx(5_000.0)

    def test_asymmetric_band_tail(self):
        """Asymmetric bands: tight up trims spike; loose down tolerates dip."""
        book = self._book(
            default_band_up=0.02, default_band_down=0.02,
            band_overrides=(("FIGI_TAIL", 0.01, 0.05),),
        )
        target = self._target({"FIGI_TAIL": 0.50})

        # Spike: realised = 0.52 → delta = -0.02 > band_up=0.01 → trigger SELL
        result_up = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_TAIL": 0.52},
        )
        assert len(result_up.orders) == 1
        assert result_up.orders[0].side == OrderSide.SELL

        # Dip: realised = 0.48 → delta = +0.02 < band_down=0.05 → suppressed
        result_down = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_TAIL": 0.48},
        )
        assert result_down.orders == ()

    def test_band_only_applied_when_realized_present(self):
        """Without realised data, band is not applied and full target is traded."""
        book = self._book(default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.01})  # tiny target within band

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights=None,
        )
        # No realised data → band not applied → trade the full target
        assert len(result.orders) == 1
        assert result.orders[0].quantity == pytest.approx(1_000.0)

    # ── cap gate — per-name ─────────────────────────────────────────────

    def test_per_name_cap_breach_band_creates_corrective_verified(self):
        """Band gate creates corrective trade for cap breach; cap gate verifies post_book."""
        book = self._book(per_name_cap=0.10, default_band_up=0.02, default_band_down=0.02)
        target = self._target({"FIGI_A": 0.08})

        # Realised = 0.12 → exceeds per_name_cap 0.10.
        # Band: delta = 0.08 - 0.12 = -0.04 > band_up=0.02 → SELL.
        # Cap gate: realised breach; already correcting → verify post_book=0.08 ≤ cap.
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.12},
        )
        assert len(result.orders) == 1
        assert result.orders[0].side == OrderSide.SELL
        # delta = -0.04 → SELL 4_000
        assert result.orders[0].quantity == pytest.approx(4_000.0)

    def test_per_name_cap_breach_band_suppressed_corrective_order(self):
        """Realised breaches per_name_cap but band suppresses trade → widen."""
        # Use wide bands so the band gate doesn't trigger on its own.
        book = self._book(per_name_cap=0.10, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": 0.08})

        # Realised = 0.12 → breaches per_name_cap 0.10.
        # Band: delta = 0.08 - 0.12 = -0.04, within band (0.10) → suppressed
        # But cap gate sees the breach and widens → corrective SELL to cap
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.12},
        )
        assert len(result.orders) == 1
        assert result.orders[0].side == OrderSide.SELL
        # Realised 0.12 → cap 0.10 → sell 0.02 * 100_000 = 2_000
        assert result.orders[0].quantity == pytest.approx(2_000.0)

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
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": -0.12},
        )
        assert len(result.orders) == 1
        assert result.orders[0].side == OrderSide.BUY
        # widen-to-compliance: cap_w = -per_name_cap = -0.10
        # delta = -0.10 - (-0.12) = +0.02 → BUY 2_000
        assert result.orders[0].quantity == pytest.approx(2_000.0)

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

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.52, "FIGI_B": 0.28},
        )
        # Drift = |0.50-0.52| + |0.30-0.28| = 0.02 + 0.02 = 0.04 < 0.05 → OK
        # But bands are wide so no orders
        assert result.orders == ()

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
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.12},
        )
        # Widen-to-compliance: sell down to cap=0.10
        assert len(result.orders) == 1
        assert result.orders[0].side == OrderSide.SELL
        assert result.orders[0].quantity == pytest.approx(2_000.0)  # (0.12-0.10)*100k

class TestRebalanceWithSizing:
    """Slice 5: sizing integration — EUR notional → native share quantity."""

    @staticmethod
    def _target(figi_to_weight: dict[str, float]) -> pd.DataFrame:
        df = pd.DataFrame(
            {k: [v] for k, v in figi_to_weight.items()},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        df.columns.name = "figi"
        return df

    # ── EUR instrument (no FX) ───────────────────────────────────────────

    def test_eur_instrument_sized(self):
        """EUR instrument with price → native share quantity."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"EUR_ETF": 0.5})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"EUR_ETF": InstrumentSizing(currency="EUR", size_increment=1.0)},
            fx_rates={"EUR": 1.0},
            prices={"EUR_ETF": 100.0},
        )

        assert len(result.orders) == 1
        # 50_000 / 100 = 500 shares
        assert result.orders[0].quantity == pytest.approx(500.0)
        assert result.orders[0].side == OrderSide.BUY

    def test_eur_instrument_sub_increment_dropped(self):
        """EUR instrument with tiny notional → sub-increment → no order."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"EUR_ETF": 0.00001})  # 0.001% of NAV = 1 EUR

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"EUR_ETF": InstrumentSizing(currency="EUR", size_increment=1.0)},
            fx_rates={"EUR": 1.0},
            prices={"EUR_ETF": 100.0},
        )

        assert len(result.orders) == 0  # 1 EUR / 100 = 0.01 → rounds to 0

    # ── USD instrument ───────────────────────────────────────────────────

    def test_usd_instrument_sized(self):
        """USD instrument: apply FX rate to convert EUR→USD notional."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"US_STOCK": 0.5})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"US_STOCK": InstrumentSizing(currency="USD", size_increment=1.0)},
            fx_rates={"USD": 1.10},
            prices={"US_STOCK": 110.0},
        )

        assert len(result.orders) == 1
        # 50_000 × 1.10 / 110 = 55_000 / 110 = 500 shares
        assert result.orders[0].quantity == pytest.approx(500.0)
        assert result.orders[0].side == OrderSide.BUY

    # ── GBP instrument ───────────────────────────────────────────────────

    def test_gbp_instrument_sized(self):
        """GBP instrument: apply GBP/EUR FX rate."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"LSE_ETF": 0.5})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"LSE_ETF": InstrumentSizing(currency="GBP", size_increment=1.0)},
            fx_rates={"GBP": 0.85},
            prices={"LSE_ETF": 85.0},
        )

        assert len(result.orders) == 1
        # 50_000 × 0.85 / 85 = 42_500 / 85 = 500 shares
        assert result.orders[0].quantity == pytest.approx(500.0)

    # ── GBp instrument (London pence) ────────────────────────────────────

    def test_gbp_pence_sized(self):
        """GBp instrument: GBP/EUR rate + 100× pence factor."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"LSE_GBP": 0.5})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"LSE_GBP": InstrumentSizing(currency="GBp", size_increment=1.0)},
            fx_rates={"GBp": 0.85},  # GBP/EUR (NOT GBp/EUR)
            prices={"LSE_GBP": 8_500.0},  # price in pence
        )

        assert len(result.orders) == 1
        # 50_000 × 0.85 × 100 / 8_500 = 4,250,000 / 8_500 = 500 shares
        assert result.orders[0].quantity == pytest.approx(500.0)

    # ── size increment rounding ──────────────────────────────────────────

    def test_rounding_to_increment(self):
        """Quantity rounds to the instrument's size_increment."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"STOCK": 0.5})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"STOCK": InstrumentSizing(currency="EUR", size_increment=100.0)},
            fx_rates={"EUR": 1.0},
            prices={"STOCK": 100.0},
        )

        assert len(result.orders) == 1
        # 50_000 / 100 = 500 → 500/100 = 5 → 5*100 = 500
        assert result.orders[0].quantity == pytest.approx(500.0)
        assert result.orders[0].quantity % 100.0 == 0.0

    def test_rounding_drops_sub_increment(self):
        """Quantity below half increment → no order emitted."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"STOCK": 0.01})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"STOCK": InstrumentSizing(currency="EUR", size_increment=100.0)},
            fx_rates={"EUR": 1.0},
            prices={"STOCK": 100.0},
        )

        # 1_000 / 100 = 10 → 10/100 = 0.1 → round(0.1)*100 = 0 → dropped
        assert len(result.orders) == 0

    # ── multi-ccy netting ────────────────────────────────────────────────

    def test_multi_ccy_sizing(self):
        """Two sleeves, overlapping FIGIs in different currencies."""
        book = make_book([
            ("trend", "trend.whl", 0.6),
            ("carry", "carry.whl", 0.4),
        ])
        trend_target = self._target({"EUR_ETF": 0.5, "US_STOCK": 0.3})
        carry_target = self._target({"EUR_ETF": -0.2, "US_STOCK": 0.1})
        # EUR_ETF: 0.6*0.5 + 0.4*(-0.2) = 0.30 - 0.08 = 0.22 → BUY
        # US_STOCK: 0.6*0.3 + 0.4*0.1 = 0.18 + 0.04 = 0.22 → BUY

        result = rebalance(
            {book.sleeves[0].name: trend_target, book.sleeves[1].name: carry_target},
            nav=100_000.0,
            book=book,
            instrument_metas={
                "EUR_ETF": InstrumentSizing(currency="EUR", size_increment=1.0),
                "US_STOCK": InstrumentSizing(currency="USD", size_increment=1.0),
            },
            fx_rates={"EUR": 1.0, "USD": 1.10},
            prices={"EUR_ETF": 100.0, "US_STOCK": 110.0},
        )

        assert len(result.orders) == 2
        by_figi = {o.figi.value: o for o in result.orders}
        # EUR_ETF: 22_000 / 100 = 220 shares
        assert by_figi["EUR_ETF"].quantity == pytest.approx(220.0)
        # US_STOCK: 22_000 × 1.10 / 110 = 24_200 / 110 = 220 shares
        assert by_figi["US_STOCK"].quantity == pytest.approx(220.0)
        for o in result.orders:
            assert o.side == OrderSide.BUY

    # ── backward compat ──────────────────────────────────────────────────

    def test_missing_sizing_params_falls_back_to_raw_notional(self):
        """When sizing params are omitted, quantity is raw EUR notional."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"ANY_FIGI": 0.5})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
        )

        assert len(result.orders) == 1
        assert result.orders[0].quantity == pytest.approx(50_000.0)  # raw EUR notional

    def test_partial_sizing_params_falls_back(self):
        """Unknown FIGI falls back to raw notional; known FIGIs are sized."""
        book = make_book([("trend", "trend.whl", 1.0)])
        target = self._target({"KNOWN": 0.5, "UNKNOWN": 0.3})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={"KNOWN": InstrumentSizing(currency="EUR", size_increment=1.0)},
            fx_rates={"EUR": 1.0},
            prices={"KNOWN": 100.0},
        )

        by_figi = {o.figi.value: o for o in result.orders}
        assert by_figi["KNOWN"].quantity == pytest.approx(500.0)  # sized
        assert by_figi["UNKNOWN"].quantity == pytest.approx(30_000.0)  # raw notional


class TestRebalanceQuarantine:
    """Slice 7: held-position quarantine — counted in gate, never traded."""

    @staticmethod
    def _target(figi_to_weight: dict[str, float]) -> pd.DataFrame:
        df = pd.DataFrame(
            {k: [v] for k, v in figi_to_weight.items()},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        df.columns.name = "figi"
        return df

    @staticmethod
    def _book(name: str = "trend", budget: float = 1.0, **kwargs) -> BookConfig:
        return BookConfig(
            sleeves=(SleeveConfig(name=SleeveName(name), wheel_filename=f"{name}.whl", budget=budget),),
            **kwargs,
        )

    # ── quarantine: no trade ─────────────────────────────────────────────

    def test_held_position_quarantined_no_order(self):
        """A held position for a FIGI not in any sleeve → quarantined, no order."""
        book = self._book()
        target = self._target({"FIGI_A": 0.50})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.50},  # at target → no delta
            held_positions={"FIGI_ORPHAN": 0.15},  # held, not in any sleeve
        )

        # Only FIGI_A at target — no order for either
        assert len(result.orders) == 0
        assert "FIGI_ORPHAN" in result.quarantined
        assert "FIGI_A" not in result.quarantined

    def test_held_position_counted_in_gross_cap(self):
        """Held position contributes to gross cap → breach raises."""
        book = self._book(gross_cap=0.50)
        target = self._target({"FIGI_A": 0.30})

        # target=0.30 + held=0.25 → gross=0.55 > 0.50 cap
        with pytest.raises(ValueError, match="Gross exposure"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={"FIGI_A": 0.30},
                held_positions={"FIGI_ORPHAN": 0.25},
            )

    def test_held_position_counted_in_net_cap(self):
        """Held position contributes to net cap → breach raises."""
        book = self._book(net_cap=0.10)
        target = self._target({"FIGI_A": -0.05})

        # target=-0.05 + held=-0.10 → net=|−0.15|=0.15 > 0.10 cap
        with pytest.raises(ValueError, match="Net exposure"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={"FIGI_A": -0.05},
                held_positions={"FIGI_ORPHAN": -0.10},
            )

    def test_held_position_within_caps_ok(self):
        """Held position within all caps → orders generated only for tradeable."""
        book = self._book(gross_cap=1.0)
        target = self._target({"FIGI_A": 0.50})

        # No realised → full target traded
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            held_positions={"FIGI_ORPHAN": 0.10},
        )

        assert len(result.orders) == 1
        assert result.orders[0].figi.value == "FIGI_A"
        assert "FIGI_ORPHAN" in result.quarantined

    def test_quarantined_per_name_cap_breach_fails_closed(self):
        """Held position breaches per-name cap → unfixable (can't trade quarantined)."""
        book = self._book(per_name_cap=0.10, default_band_up=0.10, default_band_down=0.10)
        target = self._target({"FIGI_A": 0.05})

        # Held breaches per_name_cap: 0.15 > 0.10, and it's not targetable → unfixable
        with pytest.raises(ValueError, match="quarantin"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={"FIGI_A": 0.05},
                held_positions={"FIGI_ORPHAN": 0.15},
            )

    def test_held_and_targeted_mix(self):
        """Quarantined + targeted: tradeable gets orders, quarantined doesn't."""
        book = self._book()
        target = self._target({"FIGI_A": 0.40, "FIGI_B": -0.20})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.35, "FIGI_B": -0.15},
            held_positions={"FIGI_ORPHAN": 0.10},
        )

        by_figi = {o.figi.value: o for o in result.orders}
        assert "FIGI_ORPHAN" not in by_figi  # never traded
        assert "FIGI_ORPHAN" in result.quarantined
        assert "FIGI_A" in by_figi
        assert "FIGI_B" in by_figi

    def test_held_only_no_targets(self):
        """Only held positions, no sleeve targets → quarantined, no orders."""
        book = self._book()
        # Empty target (all zeros) from a sleeve
        target = self._target({"FIGI_A": 0.0})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.0},
            held_positions={"FIGI_ORPHAN_1": 0.20, "FIGI_ORPHAN_2": -0.10},
        )

        assert len(result.orders) == 0
        assert set(result.quarantined) == {"FIGI_ORPHAN_1", "FIGI_ORPHAN_2"}

    def test_held_position_not_in_realized_not_double_counted(self):
        """Held positions are separate from realized — not double-counted in post_book."""
        book = self._book(gross_cap=0.50)
        target = self._target({"FIGI_A": 0.20})

        # realised=A:0.20 + held=ORPHAN:0.20 → gross=0.40 ≤ 0.50 cap → OK
        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            realized_weights={"FIGI_A": 0.20},
            held_positions={"FIGI_ORPHAN": 0.20},
        )

        assert len(result.orders) == 0  # at target, no delta
        assert "FIGI_ORPHAN" in result.quarantined

    def test_quarantined_counted_in_aggregate_drift(self):
        """Aggregate drift includes held-to-zero drift (held has no target)."""
        book = self._book(
            aggregate_drift_threshold=0.05,
            default_band_up=0.10,
            default_band_down=0.10,
        )
        target = self._target({"FIGI_A": 0.50})

        # Realised = 0.52 → delta=0.02 for FIGI_A
        # Held ORPHAN=0.06 → delta=|0−0.06|=0.06
        # Aggregate = 0.02 + 0.06 = 0.08 > 0.05 → fires
        with pytest.raises(ValueError, match="Aggregate drift"):
            rebalance(
                {book.sleeves[0].name: target},
                nav=100_000.0,
                book=book,
                realized_weights={"FIGI_A": 0.52},
                held_positions={"FIGI_ORPHAN": 0.06},
            )

    def test_empty_held_positions_no_quarantine(self):
        """Empty held positions → no quarantine, normal operation."""
        book = self._book()
        target = self._target({"FIGI_A": 0.50})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            held_positions={},
        )

        assert len(result.orders) == 1
        assert result.quarantined == ()

    def test_held_positions_with_sizing(self):
        """Held positions do not generate orders even when sizing params available."""
        book = self._book()
        target = self._target({"FIGI_A": 0.50})

        result = rebalance(
            {book.sleeves[0].name: target},
            nav=100_000.0,
            book=book,
            instrument_metas={
                "FIGI_A": InstrumentSizing(currency="EUR", size_increment=1.0),
                "FIGI_ORPHAN": InstrumentSizing(currency="EUR", size_increment=1.0),
            },
            fx_rates={"EUR": 1.0},
            prices={"FIGI_A": 100.0, "FIGI_ORPHAN": 50.0},
            held_positions={"FIGI_ORPHAN": 0.10},
        )

        assert len(result.orders) == 1
        # Only FIGI_A gets an order: 50_000/100 = 500 shares
        assert result.orders[0].figi.value == "FIGI_A"
        assert result.orders[0].quantity == pytest.approx(500.0)
        assert "FIGI_ORPHAN" in result.quarantined

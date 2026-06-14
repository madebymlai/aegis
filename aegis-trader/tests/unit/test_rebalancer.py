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

    def test_single_figi_buy(self):
        """A positive target weight → BUY for that NAV fraction."""
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {"BBG000B9XRY4": [0.5]},  # FIGI for VUSA.L
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        target.columns.name = "figi"
        nav = 100_000.0

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

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

        orders = rebalance(target, nav, book)

        assert orders == []

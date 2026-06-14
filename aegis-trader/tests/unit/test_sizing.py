"""Unit tests for domain/sizing.py — pure, zero Nautilus."""

import pytest

from aegis_trader.domain.sizing import InstrumentSizing, size_order


class TestSizeOrderEurInstrument:
    """EUR-denominated instrument — no FX conversion, no pence."""

    def test_eur_instrument_basic(self):
        """EUR notional / EUR price → share quantity, no FX."""
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=100.0,
            fx_rate=1.0,  # EUR→EUR
            instrument=meta,
        )
        assert qty == pytest.approx(500.0)

    def test_eur_with_rounding(self):
        """EUR notional yields fractional shares rounded to size_increment."""
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        # 50_000 / 101 ≈ 495.0495... → rounds to 495
        qty = size_order(
            notional_eur=50_000.0,
            price=101.0,
            fx_rate=1.0,
            instrument=meta,
        )
        assert qty == pytest.approx(495.0)

    def test_eur_sub_increment_no_order(self):
        """Quantity below half size_increment → None."""
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        # 10 / 100 = 0.1 → rounds to 0.0 → None
        qty = size_order(
            notional_eur=10.0,
            price=100.0,
            fx_rate=1.0,
            instrument=meta,
        )
        assert qty is None


class TestSizeOrderUsdInstrument:
    """USD-denominated instrument — FX conversion, no pence."""

    def test_usd_basic(self):
        """EUR notional × USD/EUR rate / USD price."""
        meta = InstrumentSizing(currency="USD", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=110.0,
            fx_rate=1.10,  # 1 EUR = 1.10 USD
            instrument=meta,
        )
        # 50_000 * 1.10 = 55_000 → 55_000 / 110 = 500
        assert qty == pytest.approx(500.0)

    def test_usd_rounding(self):
        meta = InstrumentSizing(currency="USD", size_increment=0.01)
        qty = size_order(
            notional_eur=50_000.0,
            price=111.0,
            fx_rate=1.10,
            instrument=meta,
        )
        # 50_000 * 1.10 / 111 = 495.495... → 495.50
        assert qty == pytest.approx(495.50)

    def test_usd_sub_increment(self):
        meta = InstrumentSizing(currency="USD", size_increment=1.0)
        qty = size_order(
            notional_eur=1.0,
            price=100.0,
            fx_rate=1.10,
            instrument=meta,
        )
        # 1 * 1.10 / 100 = 0.011 → rounds to 0.0 → None
        assert qty is None


class TestSizeOrderGbpInstrument:
    """GBP-denominated instrument — FX conversion, no pence (GBp tests below)."""

    def test_gbp_basic(self):
        """GBP: notional in EUR × GBP/EUR rate / GBP price."""
        meta = InstrumentSizing(currency="GBP", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=85.0,
            fx_rate=0.85,  # 1 EUR = 0.85 GBP
            instrument=meta,
        )
        # 50_000 * 0.85 / 85 = 42_500 / 85 = 500
        assert qty == pytest.approx(500.0)

    def test_gbp_rounding(self):
        meta = InstrumentSizing(currency="GBP", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=86.0,
            fx_rate=0.85,
            instrument=meta,
        )
        # 50_000 * 0.85 = 42_500 → 42_500 / 86 ≈ 494.186 → 494
        assert qty == pytest.approx(494.0)

    def test_gbp_sub_increment(self):
        meta = InstrumentSizing(currency="GBP", size_increment=1.0)
        qty = size_order(
            notional_eur=5.0,
            price=100.0,
            fx_rate=0.85,
            instrument=meta,
        )
        # 5 * 0.85 / 100 = 0.0425 → 0 → None
        assert qty is None


class TestSizeOrderGbpPence:
    """GBp (London pence) — FX + 100× pence factor."""

    def test_gbp_basic(self):
        """GBp: apply pence factor (100×) after GBP conversion."""
        meta = InstrumentSizing(currency="GBp", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=8_500.0,  # price in pence (same as £85.00)
            fx_rate=0.85,   # GBP/EUR (NOT GBp/EUR — sizing applies ×100)
            instrument=meta,
        )
        # 50_000 * 0.85 = 42_500 GBP notional
        # × 100 = 4,250,000 GBp notional
        # / 8,500 = 500 shares
        assert qty == pytest.approx(500.0)

    def test_gbp_rounding(self):
        meta = InstrumentSizing(currency="GBp", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=8_600.0,
            fx_rate=0.85,
            instrument=meta,
        )
        # 42_500 * 100 / 8_600 = 494.186 → 494
        assert qty == pytest.approx(494.0)

    def test_gbp_sub_increment(self):
        meta = InstrumentSizing(currency="GBp", size_increment=1.0)
        qty = size_order(
            notional_eur=0.5,
            price=8_500.0,
            fx_rate=0.85,
            instrument=meta,
        )
        # 0.5 * 0.85 * 100 / 8_500 ≈ 0.005 → 0 → None
        assert qty is None

    def test_gbp_prevent_100x_error(self):
        """GBp with correct GBP/EUR FX rate yields correct quantity.

        Using GBp/EUR=85.0 directly (without the pence factor) would give
        50_000 * 85.0 / 8_500 = 500 — same answer for this test, but only
        because the price is also in pence. The invariant is: sizing always
        applies ×100 to GBp; the FX rate must be GBP/EUR, not GBp/EUR.
        """
        meta = InstrumentSizing(currency="GBp", size_increment=1.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=8_500.0,
            fx_rate=0.85,  # GBP/EUR — correct
            instrument=meta,
        )
        assert qty == pytest.approx(500.0)


class TestSizeOrderSizeIncrement:
    """Increment rounding edge cases."""

    def test_fractional_increment(self):
        """Instruments with fractional size increments (e.g., 0.01)."""
        meta = InstrumentSizing(currency="EUR", size_increment=0.01)
        qty = size_order(
            notional_eur=50_000.0,
            price=100.0,
            fx_rate=1.0,
            instrument=meta,
        )
        assert qty == pytest.approx(500.0)

    def test_round_down(self):
        """0.45 of an increment → rounds to 0 → None."""
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        qty = size_order(
            notional_eur=45.0,
            price=100.0,
            fx_rate=1.0,
            instrument=meta,
        )
        assert qty is None

    def test_round_up(self):
        """0.51 of an increment → rounds to 1× increment."""
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        qty = size_order(
            notional_eur=51.0,
            price=100.0,
            fx_rate=1.0,
            instrument=meta,
        )
        assert qty == pytest.approx(1.0)

    def test_large_increment(self):
        """Instruments with large size increments (e.g., 100 shares)."""
        meta = InstrumentSizing(currency="EUR", size_increment=100.0)
        qty = size_order(
            notional_eur=50_000.0,
            price=100.0,
            fx_rate=1.0,
            instrument=meta,
        )
        # 50_000 / 100 = 500 → 500/100=5 → 5*100=500
        assert qty == pytest.approx(500.0)

    def test_large_increment_rounding(self):
        """Rounding with large increment."""
        meta = InstrumentSizing(currency="EUR", size_increment=100.0)
        qty = size_order(
            notional_eur=55_000.0,
            price=100.0,
            fx_rate=1.0,
            instrument=meta,
        )
        # 55_000 / 100 = 550 → 550/100=5.5 → round(5.5)*100
        # Banker's rounding: round(5.5) → 6 → 600
        assert qty is not None
        assert qty % 100.0 == 0.0  # must be a multiple of increment


class TestSizeOrderEdgeCases:
    """Invalid inputs."""

    def test_zero_notional(self):
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        assert size_order(0.0, 100.0, 1.0, meta) is None

    def test_negative_notional(self):
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        assert size_order(-100.0, 100.0, 1.0, meta) is None

    def test_zero_price(self):
        meta = InstrumentSizing(currency="EUR", size_increment=1.0)
        assert size_order(50_000.0, 0.0, 1.0, meta) is None

    def test_zero_fx_rate(self):
        meta = InstrumentSizing(currency="USD", size_increment=1.0)
        assert size_order(50_000.0, 100.0, 0.0, meta) is None

    def test_negative_fx_rate(self):
        meta = InstrumentSizing(currency="USD", size_increment=1.0)
        assert size_order(50_000.0, 100.0, -1.0, meta) is None

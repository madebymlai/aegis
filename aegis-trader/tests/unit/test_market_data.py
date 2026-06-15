"""Unit tests for NautilusMarketData — the MarketDataPort adapter (Wave C FX).

FX rates are sourced from the Nautilus Cache's *mark xrate* (settable in tests
and live, venue-decoupled, auto-inverting), returning None when unavailable so
the overlay fails closed rather than fabricating a rate.
"""

import pytest
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.currencies import EUR, GBP

from aegis_trader.data.market_data import NautilusMarketData


class TestFxRate:
    def test_fx_rate_base_to_quote(self):
        """fx_rate(base, quote) returns quote units per 1 base (EUR→GBP)."""
        cache = Cache()
        cache.set_mark_xrate(EUR, GBP, 0.85)  # 0.85 GBP per 1 EUR
        md = NautilusMarketData(cache=cache)
        assert md.fx_rate("EUR", "GBP") == pytest.approx(0.85)

    def test_fx_rate_inverse_available(self):
        cache = Cache()
        cache.set_mark_xrate(EUR, GBP, 0.85)
        md = NautilusMarketData(cache=cache)
        assert md.fx_rate("GBP", "EUR") == pytest.approx(1.0 / 0.85)

    def test_fx_rate_unset_returns_none(self):
        """No rate in the cache → None (caller fails closed, never fabricates)."""
        md = NautilusMarketData(cache=Cache())
        assert md.fx_rate("EUR", "GBP") is None

    def test_fx_rate_same_currency_is_one(self):
        md = NautilusMarketData(cache=Cache())
        assert md.fx_rate("EUR", "EUR") == pytest.approx(1.0)

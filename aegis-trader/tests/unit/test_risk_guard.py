"""Unit tests for RiskGuard — pure domain, zero Nautilus.

Validates that the RiskGuard computes per-instrument max-notional caps relative
to NAV and rejects invalid configurations.  Caps are keyed by the *resolved*
InstrumentId (Wave D): each instrument keeps its own venue, so the guard never
assumes a single book-wide venue and never reconstructs identity by string-
joining a symbol to a venue (root ADR-0007).
"""

import pytest

from aegis_trader.domain.risk_guard import (
    RiskGuard,
    RiskGuardConfig,
    compute_risk_engine_max_notionals,
)


class TestRiskGuardConfig:
    """RiskGuardConfig validation."""

    def test_defaults(self):
        cfg = RiskGuardConfig()
        assert cfg.max_notional_fraction == 0.25
        assert cfg.max_order_submit_rate == "10/00:00:01"
        assert cfg.max_order_modify_rate == "10/00:00:01"

    def test_explicit(self):
        cfg = RiskGuardConfig(
            max_notional_fraction=0.10,
            max_order_submit_rate="5/00:00:01",
            max_order_modify_rate="3/00:00:01",
        )
        assert cfg.max_notional_fraction == 0.10
        assert cfg.max_order_submit_rate == "5/00:00:01"
        assert cfg.max_order_modify_rate == "3/00:00:01"

    def test_fraction_must_be_positive(self):
        with pytest.raises(ValueError, match="must be > 0"):
            RiskGuardConfig(max_notional_fraction=0.0)
        with pytest.raises(ValueError, match="must be > 0"):
            RiskGuardConfig(max_notional_fraction=-0.1)

    def test_fraction_must_not_exceed_one(self):
        with pytest.raises(ValueError, match="must be > 0 and <= 1"):
            RiskGuardConfig(max_notional_fraction=1.01)


class TestComputeMaxNotionals:
    """compute_risk_engine_max_notionals — pure function, keyed by InstrumentId."""

    def test_single_instrument(self):
        """One instrument -> one cap = NAV x fraction, keyed by its InstrumentId."""
        result = compute_risk_engine_max_notionals(
            nav=100_000.0,
            instrument_ids=["BBG000B9XRY4.XLON"],
            fraction=0.25,
        )
        assert result == {"BBG000B9XRY4.XLON": 25_000}

    def test_instruments_on_different_venues(self):
        """Each instrument keeps its own venue — no single book-wide venue."""
        result = compute_risk_engine_max_notionals(
            nav=200_000.0,
            instrument_ids=["BBG000B9XRY4.XLON", "BBG000C6K6G9.XETR"],
            fraction=0.10,
        )
        assert result == {
            "BBG000B9XRY4.XLON": 20_000,
            "BBG000C6K6G9.XETR": 20_000,
        }

    def test_empty(self):
        """No instruments -> empty dict."""
        result = compute_risk_engine_max_notionals(
            nav=100_000.0,
            instrument_ids=[],
            fraction=0.25,
        )
        assert result == {}

    def test_zero_nav(self):
        """Zero NAV -> zero caps."""
        result = compute_risk_engine_max_notionals(
            nav=0.0,
            instrument_ids=["BBG000B9XRY4.XLON"],
            fraction=0.25,
        )
        assert result == {"BBG000B9XRY4.XLON": 0}

    def test_fraction_rounds_down_to_int(self):
        """Max notional is rounded down (int) for the RiskEngine config."""
        result = compute_risk_engine_max_notionals(
            nav=100_001.0,
            instrument_ids=["BBG000B9XRY4.XLON"],
            fraction=0.25,
        )
        # 100_001 * 0.25 = 25_000.25 -> int() = 25_000
        assert result["BBG000B9XRY4.XLON"] == 25_000


class TestRiskGuardComputesCaps:
    """RiskGuard helper API."""

    def test_compute_max_notionals_by_instrument_id(self):
        """Guard computes max notionals from resolved instrument ids + NAV."""
        guard = RiskGuard(config=RiskGuardConfig(max_notional_fraction=0.25))

        result = guard.compute_max_notionals(
            nav=100_000.0,
            instrument_ids=["BBG000B9XRY4.XLON"],
        )

        assert result == {"BBG000B9XRY4.XLON": 25_000}

    def test_rate_limits_preserved(self):
        """Rate limit configs are passed through alongside the notionals."""
        guard = RiskGuard(config=RiskGuardConfig(
            max_order_submit_rate="3/00:00:05",
            max_order_modify_rate="2/00:00:05",
        ))
        cfg = guard.risk_engine_config_dict(
            nav=100_000.0,
            instrument_ids=["BBG000B9XRY4.XLON"],
        )
        assert cfg["max_order_submit_rate"] == "3/00:00:05"
        assert cfg["max_order_modify_rate"] == "2/00:00:05"
        assert cfg["max_notional_per_order"] == {"BBG000B9XRY4.XLON": 25_000}

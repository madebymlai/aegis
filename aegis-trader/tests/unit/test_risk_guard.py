"""Unit tests for RiskGuard — pure domain, zero Nautilus.

Validates that the RiskGuard correctly computes per-FIGI max-notional
caps relative to NAV and rejects invalid configurations.
"""

import pytest

from aegis_trader.domain.risk_guard import (
    RiskGuard,
    RiskGuardConfig,
    compute_risk_engine_max_notionals,
)
from aegis_trader.domain.types import SleeveName


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
    """compute_risk_engine_max_notionals — pure function."""

    def test_single_figi(self):
        """One FIGI → one cap = NAV × fraction."""
        result = compute_risk_engine_max_notionals(
            nav=100_000.0,
            figis=["BBG000B9XRY4"],
            default_venue="XLON",
            fraction=0.25,
        )
        assert result == {"BBG000B9XRY4.XLON": 25_000}

    def test_multiple_figis_same_cap(self):
        """Each FIGI gets the same max notional."""
        result = compute_risk_engine_max_notionals(
            nav=200_000.0,
            figis=["FIGI_A", "FIGI_B", "FIGI_C"],
            default_venue="XLON",
            fraction=0.10,
        )
        assert result == {
            "FIGI_A.XLON": 20_000,
            "FIGI_B.XLON": 20_000,
            "FIGI_C.XLON": 20_000,
        }

    def test_different_venue(self):
        """The venue is reflected in the InstrumentId string keys."""
        result = compute_risk_engine_max_notionals(
            nav=100_000.0,
            figis=["BBG000B9XRY4"],
            default_venue="XETR",
            fraction=0.25,
        )
        assert result == {"BBG000B9XRY4.XETR": 25_000}

    def test_empty_figis(self):
        """Empty FIGI list → empty dict."""
        result = compute_risk_engine_max_notionals(
            nav=100_000.0,
            figis=[],
            default_venue="XLON",
            fraction=0.25,
        )
        assert result == {}

    def test_zero_nav(self):
        """Zero NAV → zero caps."""
        result = compute_risk_engine_max_notionals(
            nav=0.0,
            figis=["BBG000B9XRY4"],
            default_venue="XLON",
            fraction=0.25,
        )
        assert result == {"BBG000B9XRY4.XLON": 0}

    def test_duplicate_figis(self):
        """Duplicate FIGIs produce one key (last-write wins behavior, all same value)."""
        result = compute_risk_engine_max_notionals(
            nav=100_000.0,
            figis=["FIGI_A", "FIGI_A"],
            default_venue="XLON",
            fraction=0.25,
        )
        assert result == {"FIGI_A.XLON": 25_000}


class TestRiskGuardFromBook:
    """RiskGuard.from_book_config integration."""

    @staticmethod
    def _make_book(sleeves=1, figi="BBG000B9XRY4"):
        from aegis_trader.domain.book_config import BookConfig, SleeveConfig
        return BookConfig(
            sleeves=tuple(
                SleeveConfig(
                    name=SleeveName(f"slv{i}"),
                    wheel_filename=f"slv{i}.whl",
                    budget=1.0 / sleeves,
                )
                for i in range(sleeves)
            ),
            default_venue="XLON",
        )

    def test_single_sleeve_single_figi(self):
        """Guard computes max notionals from book + NAV."""
        guard = RiskGuard(config=RiskGuardConfig(max_notional_fraction=0.25))

        result = guard.compute_max_notionals(
            nav=100_000.0,
            figis=["BBG000B9XRY4"],
            default_venue="XLON",
        )

        assert result == {"BBG000B9XRY4.XLON": 25_000}

    def test_fraction_rounds_down_to_int(self):
        """Max notional is rounded down (int) for the RiskEngine config."""
        guard = RiskGuard(config=RiskGuardConfig(max_notional_fraction=0.25))
        result = guard.compute_max_notionals(
            nav=100_001.0,
            figis=["BBG000B9XRY4"],
            default_venue="XLON",
        )
        # 100_001 * 0.25 = 25_000.25 → int() = 25_000
        assert result["BBG000B9XRY4.XLON"] == 25_000

    def test_rate_limits_preserved(self):
        """Rate limit configs are passed through."""
        guard = RiskGuard(config=RiskGuardConfig(
            max_order_submit_rate="3/00:00:05",
            max_order_modify_rate="2/00:00:05",
        ))
        cfg = guard.risk_engine_config_dict(
            nav=100_000.0,
            figis=["BBG000B9XRY4"],
            default_venue="XLON",
        )
        assert cfg["max_order_submit_rate"] == "3/00:00:05"
        assert cfg["max_order_modify_rate"] == "2/00:00:05"
        assert cfg["max_notional_per_order"] == {"BBG000B9XRY4.XLON": 25_000}

"""Unit tests for the pure-domain account-integrity check — zero Nautilus."""


from aegis_trader.domain.integrity import check_account_integrity


class TestCheckAccountIntegrity:
    """Account-integrity rule: one deterministic rule per scope."""

    def test_all_healthy(self):
        """All checks pass → healthy."""
        report = check_account_integrity(
            nav=100_000.0,
            cash=99_000.0,
            nav_tolerance_fraction=0.05,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is True
        assert report.reason is None

    def test_account_id_mismatch(self):
        """Wrong account ID → unhealthy."""
        report = check_account_integrity(
            nav=100_000.0,
            cash=99_000.0,
            expected_account_id="U1234567",
            actual_account_id="U9999999",
            cache_healthy=True,
        )
        assert report.healthy is False
        assert "account" in report.reason.lower()

    def test_cache_hydration_failure(self):
        """Cache failed to hydrate → unhealthy."""
        report = check_account_integrity(
            nav=100_000.0,
            cash=99_000.0,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=False,
        )
        assert report.healthy is False
        assert "cache" in report.reason.lower()

    def test_nav_zero_or_negative_unhealthy(self):
        """NAV ≤ 0 is unhealthy regardless of other checks."""
        report = check_account_integrity(
            nav=0.0,
            cash=0.0,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is False
        assert "nav" in report.reason.lower()

    def test_nav_cash_mismatch_within_band_healthy(self):
        """NAV and cash within tolerance band → healthy."""
        # NAV=100_000, cash=95_000 → difference=5_000 = 5% of NAV
        # tolerance=10% → OK
        report = check_account_integrity(
            nav=100_000.0,
            cash=95_000.0,
            nav_tolerance_fraction=0.10,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is True

    def test_nav_cash_mismatch_beyond_band_unhealthy(self):
        """NAV and cash gap beyond tolerance band → unhealthy."""
        # NAV=100_000, cash=85_000 → difference=15_000 = 15% of NAV
        # tolerance=10% → unhealthy
        report = check_account_integrity(
            nav=100_000.0,
            cash=85_000.0,
            nav_tolerance_fraction=0.10,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is False
        assert "nav" in report.reason.lower() or "cash" in report.reason.lower()

    def test_tolerance_zero_requires_exact_match(self):
        """Zero tolerance → NAV must equal cash exactly."""
        report = check_account_integrity(
            nav=100_000.0,
            cash=100_000.01,  # one cent off
            nav_tolerance_fraction=0.0,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is False

    def test_none_account_ids_skipped(self):
        """When either account ID is None, the check is skipped."""
        report = check_account_integrity(
            nav=100_000.0,
            cash=99_000.0,
            nav_tolerance_fraction=0.10,
            expected_account_id=None,
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is True

        report2 = check_account_integrity(
            nav=100_000.0,
            cash=99_000.0,
            nav_tolerance_fraction=0.10,
            expected_account_id="U1234567",
            actual_account_id=None,
            cache_healthy=True,
        )
        assert report2.healthy is True

    def test_default_tolerance_is_conservative(self):
        """Default nav_tolerance_fraction is 0.0 (exact match)."""
        report = check_account_integrity(
            nav=100_000.0,
            cash=100_000.0,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report.healthy is True

        report2 = check_account_integrity(
            nav=100_000.0,
            cash=99_999.0,
            expected_account_id="U1234567",
            actual_account_id="U1234567",
            cache_healthy=True,
        )
        assert report2.healthy is False

    def test_multiple_failures_reports_first(self):
        """When multiple checks fail, the first one found is reported."""
        report = check_account_integrity(
            nav=0.0,  # first failure: NAV ≤ 0
            cash=0.0,
            expected_account_id="U1234567",
            actual_account_id="U9999999",
            cache_healthy=False,
        )
        assert report.healthy is False
        assert report.reason is not None

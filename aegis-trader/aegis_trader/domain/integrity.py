"""Account-integrity check — one deterministic rule per scope.

Pure domain component: checks account-level invariants (account ID,
cache hydration, NAV/cash consistency) and returns an IntegrityReport.
Zero Nautilus — the Strategy calls this at startup; a failed report
halts the book globally.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrityReport:
    """Result of an account-integrity check.

    *healthy* is True when all checks pass.
    *reason* is a human-readable explanation of the first failure (None when healthy).
    """

    healthy: bool
    reason: str | None = None


def check_account_integrity(
    *,
    nav: float,
    cash: float,
    nav_tolerance_fraction: float = 0.0,
    expected_account_id: str | None = None,
    actual_account_id: str | None = None,
    cache_healthy: bool = True,
) -> IntegrityReport:
    """Check account-level invariants — one deterministic rule per scope.

    Checks (in order):
      1. NAV > 0 (must be positive)
      2. Cache hydrated (no data load failure at startup)
      3. Account ID matches (when both are provided)
      4. |NAV − cash| ≤ NAV × nav_tolerance_fraction

    Returns the first failure found; a healthy report has reason=None.

    *nav* — portfolio net asset value (EUR).
    *cash* — account cash balance (EUR).
    *nav_tolerance_fraction* — max allowed |NAV − cash| as fraction of NAV.
      0.0 (default) requires exact equality.
    *expected_account_id* — the account id expected by config.
    *actual_account_id* — the account id reported by the broker.
    *cache_healthy* — True if the Nautilus Cache hydrated without errors.
    """
    if nav <= 0.0:
        return IntegrityReport(
            healthy=False,
            reason=f"NAV must be positive; got {nav:.2f}",
        )

    if not cache_healthy:
        return IntegrityReport(
            healthy=False,
            reason="Cache hydration failed — account state is untrustworthy",
        )

    if expected_account_id is not None and actual_account_id is not None:
        if expected_account_id != actual_account_id:
            return IntegrityReport(
                healthy=False,
                reason=(
                    f"Account ID mismatch: expected {expected_account_id!r}, "
                    f"got {actual_account_id!r}"
                ),
            )

    max_gap = nav * nav_tolerance_fraction
    gap = abs(nav - cash)
    if gap > max_gap:
        return IntegrityReport(
            healthy=False,
            reason=(
                f"NAV/cash mismatch: NAV={nav:.2f}, cash={cash:.2f}, "
                f"gap={gap:.2f} exceeds tolerance {max_gap:.2f} "
                f"(fraction={nav_tolerance_fraction})"
            ),
        )

    return IntegrityReport(healthy=True)

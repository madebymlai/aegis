"""RiskGuard — NAV-relative order-level risk caps.

Pure-domain component: computes per-instrument max‑notional caps as a
fraction of NAV and assembles them into a form suitable for the Nautilus
``RiskEngineConfig``.  Defense-in-depth over the sizing layer — the RiskEngine
denies any single order whose notional exceeds the cap.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskGuardConfig:
    """Static configuration for the RiskGuard."""

    max_notional_fraction: float = 0.25
    """Max notional per order, expressed as fraction of NAV (0 < x ≤ 1)."""

    max_order_submit_rate: str = "10/00:00:01"
    """Max order submission rate per timedelta."""

    max_order_modify_rate: str = "10/00:00:01"
    """Max order modification rate per timedelta."""

    def __post_init__(self) -> None:
        if not (0 < self.max_notional_fraction <= 1.0):
            raise ValueError(
                f"max_notional_fraction must be > 0 and <= 1; got {self.max_notional_fraction!r}"
            )


class RiskGuard:
    """Compute per-instrument max-notional caps from NAV.

    Produces a dict suitable for ``RiskEngineConfig.max_notional_per_order``
    (InstrumentId string → max notional as int), plus rate limits.
    """

    def __init__(self, config: RiskGuardConfig | None = None) -> None:
        self._config = config or RiskGuardConfig()

    @property
    def config(self) -> RiskGuardConfig:
        return self._config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_max_notionals(
        self,
        *,
        nav: float,
        instrument_ids: list[str],
    ) -> dict[str, int]:
        """Return a mapping of ``InstrumentId-string -> max notional (int)``."""
        return compute_risk_engine_max_notionals(
            nav=nav,
            instrument_ids=instrument_ids,
            fraction=self._config.max_notional_fraction,
        )

    def risk_engine_config_dict(
        self,
        *,
        nav: float,
        instrument_ids: list[str],
    ) -> dict:
        """Return a dict suitable for ``RiskEngineConfig(...)`` kwargs."""
        return {
            "max_order_submit_rate": self._config.max_order_submit_rate,
            "max_order_modify_rate": self._config.max_order_modify_rate,
            "max_notional_per_order": self.compute_max_notionals(
                nav=nav, instrument_ids=instrument_ids,
            ),
        }


# ------------------------------------------------------------------
# Free function (pure, no class state needed)
# ------------------------------------------------------------------


def compute_risk_engine_max_notionals(
    *,
    nav: float,
    instrument_ids: list[str],
    fraction: float,
) -> dict[str, int]:
    """Pure function: compute max notional per instrument as NAV x fraction.

    Keyed by the *resolved* InstrumentId string (e.g. ``"BBG...XLON"``), so each
    instrument carries its own venue and identity is never reconstructed by
    string-joining a FIGI to a book-wide venue (ADR-0002).
    """
    cap = int(nav * fraction)
    return {instrument_id: cap for instrument_id in instrument_ids}

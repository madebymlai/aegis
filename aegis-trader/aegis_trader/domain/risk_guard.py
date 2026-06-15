"""RiskGuard — NAV-relative order-level risk caps.

Pure-domain component: computes per-instrument max‑notional caps as a
fraction of NAV and assembles them into a form suitable for the Nautilus
``RiskEngineConfig``.  Defense-in-depth over the sizing layer — the RiskEngine
denies any single order whose notional exceeds the cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
        figis: list[str],
        default_venue: str,
    ) -> dict[str, int]:
        """Return a mapping of ``InstrumentId-string → max notional (int)``."""
        return compute_risk_engine_max_notionals(
            nav=nav,
            figis=figis,
            default_venue=default_venue,
            fraction=self._config.max_notional_fraction,
        )

    def risk_engine_config_dict(
        self,
        *,
        nav: float,
        figis: list[str],
        default_venue: str,
    ) -> dict:
        """Return a dict suitable for ``RiskEngineConfig(...)`` kwargs."""
        return {
            "max_order_submit_rate": self._config.max_order_submit_rate,
            "max_order_modify_rate": self._config.max_order_modify_rate,
            "max_notional_per_order": self.compute_max_notionals(
                nav=nav, figis=figis, default_venue=default_venue,
            ),
        }


# ------------------------------------------------------------------
# Free function (pure, no class state needed)
# ------------------------------------------------------------------


def compute_risk_engine_max_notionals(
    *,
    nav: float,
    figis: list[str],
    default_venue: str,
    fraction: float,
) -> dict[str, int]:
    """Pure function: compute max notional per instrument as NAV × fraction.

    Returns dict mapping ``{figi}.{venue}`` → int max notional.
    """
    cap = int(nav * fraction)
    return {f"{figi}.{default_venue}": cap for figi in figis}

"""Book Config — the Trader-owned, declarative specification that fully defines
the Commingled Book.

Declares one or more sleeves, each bound to a content-addressed wheel filename
with a static risk share and risk group, plus the book's risk controls (vol
target, caps, bands, per-instrument overrides, aggregate-drift threshold).  Cap
*provenance* — that the caps never exceed what research validated — is grounded
in the sleeves' bundles and checked at load by
``bundles.provenance.check_cap_provenance``, not on this config.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from aegis_trader.domain.types import SleeveName

_EPS = 1e-12


class RiskGroup(StrEnum):
    """Top-level risk-budget group for a sleeve."""

    FLOOR = "Floor"
    TARGET = "Target"
    EXPANSION = "Expansion"


@dataclass(frozen=True)
class DrawdownDeleverCurve:
    """Book-level exposure multiplier as realized drawdown deepens.

    The curve is deliberately one-way risk conditioning: it maps the current
    realized drawdown to a scalar in ``[floor_multiplier, 1]`` and is applied to
    the whole allocator output.  It never increases exposure above the
    vol-targeted allocation.
    """

    start_drawdown: float
    end_drawdown: float
    floor_multiplier: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.start_drawdown)
            or self.start_drawdown < 0.0
            or self.start_drawdown >= 1.0
        ):
            raise ValueError("start_drawdown must be finite in [0, 1)")
        if (
            not math.isfinite(self.end_drawdown)
            or self.end_drawdown <= self.start_drawdown
            or self.end_drawdown > 1.0
        ):
            raise ValueError("end_drawdown must be finite and greater than start_drawdown, up to 1")
        if (
            not math.isfinite(self.floor_multiplier)
            or self.floor_multiplier < 0.0
            or self.floor_multiplier > 1.0
        ):
            raise ValueError("floor_multiplier must be finite in [0, 1]")

    def multiplier_for(self, drawdown: float) -> float:
        """Return the exposure multiplier for a realized drawdown fraction."""
        if not math.isfinite(drawdown):
            raise ValueError("drawdown must be finite")
        bounded = min(max(float(drawdown), 0.0), 1.0)
        if bounded <= self.start_drawdown:
            return 1.0
        if bounded >= self.end_drawdown:
            return self.floor_multiplier
        progress = (bounded - self.start_drawdown) / (
            self.end_drawdown - self.start_drawdown
        )
        return 1.0 - progress * (1.0 - self.floor_multiplier)


@dataclass(frozen=True)
class SleeveConfig:
    """One sleeve in the book — a notional sub-portfolio backed by one bundle.

    Caps are *not* declared per sleeve here: the research-validated ceiling lives
    in the sleeve's bundle (``LockedExecutionPlan`` gross/net caps) and is
    enforced at load by ``bundles.provenance.check_cap_provenance`` (B13) — never
    an operator-entered field compared against the operator's own caps.
    """

    name: SleeveName
    wheel_filename: str
    risk_share: float
    group: RiskGroup = RiskGroup.FLOOR
    weight_band_down: float = 0.0
    weight_band_up: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.risk_share) or self.risk_share < 0:
            raise ValueError(
                f"sleeve {self.name.value!r} risk_share must be finite and non-negative"
            )
        if not isinstance(self.group, RiskGroup):
            object.__setattr__(self, "group", RiskGroup(self.group))
        for label, value in (
            ("weight_band_down", self.weight_band_down),
            ("weight_band_up", self.weight_band_up),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"sleeve {self.name.value!r} {label} must be finite and non-negative"
                )


@dataclass(frozen=True)
class BookConfig:
    """The full Commingled Book declaration.

    Risk controls: book volatility target, gross/net/per-name caps, asymmetric
    drift bands with per-instrument overrides, and a book-level aggregate drift
    threshold.  Cap *provenance* — that these caps never exceed what research
    validated — is a bundle-grounded load-time check
    (``bundles.provenance.check_cap_provenance``), not a self-referential field
    on this config.
    """

    sleeves: tuple[SleeveConfig, ...]
    base_currency: str = "EUR"
    book_vol_target: float = 0.09
    sleeve_reversion_fraction: float = 1.0
    drawdown_delever: DrawdownDeleverCurve | None = None

    # Gross cap stays authoritative after risk-budget scaling.  It is no longer
    # derived from static capital budgets; the allocator produces the requested
    # weights and the rebalancer's cap gate validates the post-band book.
    max_book_gross: float = 1.0

    # ── caps (all as fractions of NAV) ──
    gross_cap: float | None = None   # max Σ|w_i|
    net_cap: float | None = None     # max |Σ w_i|
    per_name_cap: float | None = None  # max |w_i| per instrument

    # ── bands ──
    default_band_up: float = 0.02    # symmetric default: ±2%
    default_band_down: float = 0.02
    # Per-FIGI asymmetric overrides: [(figi, band_up, band_down), ...]
    band_overrides: tuple[tuple[str, float, float], ...] = ()

    # ── aggregate fidelity ──
    aggregate_drift_threshold: float | None = None  # max Σ|w_realized - w_target|

    def __post_init__(self) -> None:
        if not self.sleeves:
            raise ValueError("BookConfig must declare at least one sleeve")
        names = [s.name.value for s in self.sleeves]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate sleeve names in BookConfig: {names}")
        if not math.isfinite(self.book_vol_target) or self.book_vol_target <= 0:
            raise ValueError("book_vol_target must be finite and positive")
        if (
            not math.isfinite(self.sleeve_reversion_fraction)
            or self.sleeve_reversion_fraction <= 0
            or self.sleeve_reversion_fraction > 1
        ):
            raise ValueError("sleeve_reversion_fraction must be in (0, 1]")
        if not math.isfinite(self.max_book_gross) or self.max_book_gross <= 0:
            raise ValueError("max_book_gross must be finite and positive")
        if sum(s.risk_share for s in self.sleeves) <= _EPS:
            raise ValueError("BookConfig must allocate positive total risk_share")

    @property
    def sleeve_count(self) -> int:
        return len(self.sleeves)

    def band_for(self, figi: str) -> tuple[float, float]:
        """Return (band_up, band_down) for *figi*, honouring overrides."""
        for override_figi, up, down in self.band_overrides:
            if override_figi == figi:
                return (up, down)
        return (self.default_band_up, self.default_band_down)

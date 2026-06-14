"""Book Config — the Trader-owned, declarative specification that fully defines
the Commingled Book.

Declares one or more sleeves, each bound to a content-addressed wheel filename
with a static budget.  Caps, bands, per-instrument overrides, and
research-validated cap provenance assertion arrive in Slice 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegis_trader.domain.types import SleeveName


@dataclass(frozen=True)
class SleeveConfig:
    """One sleeve in the book — a notional sub-portfolio backed by one bundle."""

    name: SleeveName
    wheel_filename: str
    budget: float  # fraction of book NAV notionally allocated (≤ 1.0)
    research_validated_cap: float | None = None  # max per-name cap from the bundle manifest


@dataclass(frozen=True)
class BookConfig:
    """The full Commingled Book declaration.

    Slice 4 adds risk controls: gross/net/per-name caps, asymmetric drift
    bands with per-instrument overrides, a book-level aggregate drift
    threshold, and a provenance assertion that the Book Config's per-name
    cap never exceeds any sleeve's research-validated cap.
    """

    sleeves: tuple[SleeveConfig, ...]
    base_currency: str = "EUR"
    default_venue: str = "XLON"

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

        # Provenance assertion: per_name_cap ≤ each sleeve's research-validated cap.
        if self.per_name_cap is not None:
            for s in self.sleeves:
                rvc = s.research_validated_cap
                if rvc is not None and self.per_name_cap > rvc:
                    raise ValueError(
                        f"BookConfig per_name_cap ({self.per_name_cap}) exceeds "
                        f"sleeve '{s.name.value}' research-validated cap ({rvc})"
                    )

    @property
    def sleeve_count(self) -> int:
        return len(self.sleeves)

    def band_for(self, figi: str) -> tuple[float, float]:
        """Return (band_up, band_down) for *figi*, honouring overrides."""
        for override_figi, up, down in self.band_overrides:
            if override_figi == figi:
                return (up, down)
        return (self.default_band_up, self.default_band_down)

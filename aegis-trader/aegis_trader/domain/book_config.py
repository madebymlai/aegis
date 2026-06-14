"""Book Config — the Trader-owned, declarative specification that fully defines
the Commingled Book.

Declares one or more sleeves, each bound to a content-addressed wheel filename
with a static budget.  Caps, bands, and per-instrument overrides arrive in
later slices.
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


@dataclass(frozen=True)
class BookConfig:
    """The full Commingled Book declaration.

    Inert — it selects trusted artifacts and parameters only; it is the live
    counterpart of Aegis RD's Run Config.
    """

    sleeves: tuple[SleeveConfig, ...]
    base_currency: str = "EUR"
    default_venue: str = "XLON"

    def __post_init__(self) -> None:
        if not self.sleeves:
            raise ValueError("BookConfig must declare at least one sleeve")
        names = [s.name.value for s in self.sleeves]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate sleeve names in BookConfig: {names}")

    @property
    def sleeve_count(self) -> int:
        return len(self.sleeves)

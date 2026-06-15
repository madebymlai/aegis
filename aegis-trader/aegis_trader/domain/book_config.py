"""Book Config — the Trader-owned, declarative specification that fully defines
the Commingled Book.

Declares one or more sleeves, each bound to a content-addressed wheel filename
with a static budget, plus the book's risk controls (caps, bands, per-instrument
overrides, aggregate-drift threshold).  Cap *provenance* — that the caps never
exceed what research validated — is grounded in the sleeves' bundles and checked
at load by ``bundles.provenance.check_cap_provenance``, not on this config.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegis_trader.domain.types import SleeveName


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
    budget: float  # fraction of book NAV notionally allocated (<= 1.0)
    venue: str | None = None  # per-sleeve venue override (defaults to BookConfig.default_venue)


@dataclass(frozen=True)
class BookConfig:
    """The full Commingled Book declaration.

    Risk controls: gross/net/per-name caps, asymmetric drift bands with
    per-instrument overrides, and a book-level aggregate drift threshold.  Cap
    *provenance* — that these caps never exceed what research validated — is a
    bundle-grounded load-time check (``bundles.provenance.check_cap_provenance``),
    not a self-referential field on this config.
    """

    sleeves: tuple[SleeveConfig, ...]
    base_currency: str = "EUR"
    default_venue: str = "XLON"

    # Book gross = Σ sleeve budgets.  Defaults to 1.0 (fully invested, no
    # leverage, ADR-0001); raise explicitly to run levered.
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

        # Book gross = Σ budgets must not exceed the configured max (ADR-0001:
        # sleeve budgets sum to the book gross; >1.0 is leverage and must be
        # opted into by raising max_book_gross).
        book_gross = sum(s.budget for s in self.sleeves)
        if book_gross > self.max_book_gross + 1e-9:
            raise ValueError(
                f"book gross (Σ budgets = {book_gross:.4f}) exceeds "
                f"max_book_gross ({self.max_book_gross:.4f}); raise max_book_gross "
                f"to run levered"
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

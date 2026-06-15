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
from collections.abc import Mapping
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
class ConvexityBudgetCandidate:
    """One operator-scored Target hedge candidate for convexity-unit sizing."""

    sleeve: SleeveName
    expected_annual_payoff: float
    annual_carry: float
    crisis_reliability: float
    convexity_units_per_risk_share: float
    capacity_risk_share: float

    def __post_init__(self) -> None:
        if not isinstance(self.sleeve, SleeveName):
            object.__setattr__(self, "sleeve", SleeveName(self.sleeve))
        _validate_non_negative(
            self.expected_annual_payoff,
            f"tail candidate {self.sleeve.value!r} expected_annual_payoff",
        )
        _validate_positive(
            self.annual_carry,
            f"tail candidate {self.sleeve.value!r} annual_carry",
        )
        if (
            not math.isfinite(self.crisis_reliability)
            or not 0.0 <= self.crisis_reliability <= 1.0
        ):
            raise ValueError(
                f"tail candidate {self.sleeve.value!r} crisis_reliability "
                "must be in [0, 1]"
            )
        _validate_positive(
            self.convexity_units_per_risk_share,
            f"tail candidate {self.sleeve.value!r} convexity_units_per_risk_share",
        )
        _validate_non_negative(
            self.capacity_risk_share,
            f"tail candidate {self.sleeve.value!r} capacity_risk_share",
        )

    @property
    def efficiency(self) -> float:
        """Convex payoff per unit carry, reliability-adjusted."""
        return (
            self.expected_annual_payoff
            / self.annual_carry
            * self.crisis_reliability
        )


@dataclass(frozen=True)
class TailConvexityBudget:
    """Target-group budget expressed in convexity units, not live signals."""

    coverage_target_units: float
    unit_payoff_fraction_at_20_down: float
    candidates: tuple[ConvexityBudgetCandidate, ...]

    def __post_init__(self) -> None:
        _validate_non_negative(
            self.coverage_target_units,
            "tail convexity coverage_target_units",
        )
        _validate_positive(
            self.unit_payoff_fraction_at_20_down,
            "tail convexity unit_payoff_fraction_at_20_down",
        )
        sleeves = [candidate.sleeve for candidate in self.candidates]
        if len(sleeves) != len(set(sleeves)):
            labels = [sleeve.value for sleeve in sleeves]
            raise ValueError(f"duplicate tail convexity candidates: {labels}")
        if self.coverage_target_units > _EPS and not self.candidates:
            raise ValueError(
                "tail convexity budget with positive coverage needs candidates"
            )

    def risk_shares(self) -> dict[SleeveName, float]:
        """Fill highest-efficiency candidates first to the coverage target."""
        remaining_units = self.coverage_target_units
        allocations: dict[SleeveName, float] = {}
        for candidate in sorted(
            self.candidates,
            key=lambda c: (-c.efficiency, c.sleeve.value),
        ):
            if remaining_units <= _EPS:
                break
            capacity = candidate.capacity_risk_share
            if capacity <= _EPS:
                continue
            needed = remaining_units / candidate.convexity_units_per_risk_share
            risk_share = min(capacity, needed)
            if risk_share <= _EPS:
                continue
            allocations[candidate.sleeve] = risk_share
            remaining_units -= risk_share * candidate.convexity_units_per_risk_share
        return allocations


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

    def __post_init__(self) -> None:
        if not math.isfinite(self.risk_share) or self.risk_share < 0:
            raise ValueError(
                f"sleeve {self.name.value!r} risk_share must be finite and non-negative"
            )
        if not isinstance(self.group, RiskGroup):
            object.__setattr__(self, "group", RiskGroup(self.group))


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

    # ── Target tail convexity budget ──
    tail_convexity_budget: TailConvexityBudget | None = None

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
        if not math.isfinite(self.max_book_gross) or self.max_book_gross <= 0:
            raise ValueError("max_book_gross must be finite and positive")
        self._validate_tail_convexity_budget()
        if sum(self.allocator_risk_shares().values()) <= _EPS:
            raise ValueError("BookConfig must allocate positive total risk_share")

    @property
    def sleeve_count(self) -> int:
        return len(self.sleeves)

    def allocator_risk_shares(self) -> dict[SleeveName, float]:
        """Return risk shares consumed by the allocator.

        Floor sleeves use their declared static shares.  Target sleeves are
        overridden by the slow-reviewed convexity-unit budget when supplied.
        Expansion sleeves consume zero risk by default until a later slice gives
        them an explicit budget.
        """
        shares = {sleeve.name: sleeve.risk_share for sleeve in self.sleeves}
        for sleeve in self.sleeves:
            if sleeve.group == RiskGroup.EXPANSION:
                shares[sleeve.name] = 0.0

        if self.tail_convexity_budget is not None:
            for sleeve in self.sleeves:
                if sleeve.group == RiskGroup.TARGET:
                    shares[sleeve.name] = 0.0
            shares.update(self.tail_convexity_budget.risk_shares())

        return shares

    def band_for(self, figi: str) -> tuple[float, float]:
        """Return (band_up, band_down) for *figi*, honouring overrides."""
        for override_figi, up, down in self.band_overrides:
            if override_figi == figi:
                return (up, down)
        return (self.default_band_up, self.default_band_down)

    def _validate_tail_convexity_budget(self) -> None:
        if self.tail_convexity_budget is None:
            return
        sleeve_by_name: Mapping[SleeveName, SleeveConfig] = {
            sleeve.name: sleeve for sleeve in self.sleeves
        }
        for candidate in self.tail_convexity_budget.candidates:
            sleeve = sleeve_by_name.get(candidate.sleeve)
            if sleeve is None:
                raise ValueError(
                    "tail convexity candidate references unknown sleeve "
                    f"{candidate.sleeve.value!r}"
                )
            if sleeve.group != RiskGroup.TARGET:
                raise ValueError(
                    "tail convexity candidate must reference a Target sleeve: "
                    f"{candidate.sleeve.value!r}"
                )


def _validate_positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")


def _validate_non_negative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and non-negative")

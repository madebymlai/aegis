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
class ConvexityBudgetCandidate:
    """One operator-scored Target hedge candidate.

    All quantities are expressed *per unit of the sleeve's risk share* — the
    lever the allocator pulls: ``payoff_at_attachment`` is the book-NAV fraction
    the candidate delivers at the budget's attachment (stress) move, and
    ``annual_carry`` is the NAV fraction it bleeds per year, both per unit risk
    share.  These are operator-supplied forecasts (calibrated and signed off at
    re-validation), never measured live in Trader.
    """

    sleeve: SleeveName
    payoff_at_attachment: float
    annual_carry: float
    crisis_reliability: float
    capacity_risk_share: float

    def __post_init__(self) -> None:
        if not isinstance(self.sleeve, SleeveName):
            object.__setattr__(self, "sleeve", SleeveName(self.sleeve))
        _validate_positive(
            self.payoff_at_attachment,
            f"tail candidate {self.sleeve.value!r} payoff_at_attachment",
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
        _validate_non_negative(
            self.capacity_risk_share,
            f"tail candidate {self.sleeve.value!r} capacity_risk_share",
        )

    @property
    def efficiency(self) -> float:
        """Crisis payoff per unit carry, reliability-adjusted (pay-off efficiency)."""
        return (
            self.payoff_at_attachment
            / self.annual_carry
            * self.crisis_reliability
        )


@dataclass(frozen=True)
class TailConvexityBudget:
    """Target-group budget sized by a fixed convexity premium, not live signals.

    Coverage is denominated directly in book NAV delivered at ``attachment``
    (the stress move the protection is defined against, e.g. ``-0.20``).
    Candidates are ranked by efficiency and filled to ``coverage_target``, each
    capped by its own ``capacity_risk_share`` and, collectively, by the optional
    ``annual_carry_budget`` premium ceiling — so either the coverage target or
    the premium budget can bind first.  Reviewed on a slow (~quarterly) cadence;
    never sized up on a live regime/dispersion/valuation signal.
    """

    attachment: float
    coverage_target: float
    candidates: tuple[ConvexityBudgetCandidate, ...]
    annual_carry_budget: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.attachment) or not -1.0 < self.attachment < 0.0:
            raise ValueError("tail convexity attachment must be a move in (-1, 0)")
        _validate_non_negative(
            self.coverage_target,
            "tail convexity coverage_target",
        )
        if self.annual_carry_budget is not None:
            _validate_positive(
                self.annual_carry_budget,
                "tail convexity annual_carry_budget",
            )
        sleeves = [candidate.sleeve for candidate in self.candidates]
        if len(sleeves) != len(set(sleeves)):
            labels = [sleeve.value for sleeve in sleeves]
            raise ValueError(f"duplicate tail convexity candidates: {labels}")
        if self.coverage_target > _EPS and not self.candidates:
            raise ValueError(
                "tail convexity budget with positive coverage needs candidates"
            )

    def risk_shares(self) -> dict[SleeveName, float]:
        """Fill highest-efficiency candidates first to the coverage target.

        Each candidate is capped by its own ``capacity_risk_share`` and by the
        running ``annual_carry_budget`` (when set); the fill stops once the
        coverage target is met or no candidate can add more within the premium
        budget.
        """
        remaining_coverage = self.coverage_target
        remaining_carry = self.annual_carry_budget
        allocations: dict[SleeveName, float] = {}
        for candidate in sorted(
            self.candidates,
            key=lambda c: (-c.efficiency, c.sleeve.value),
        ):
            if remaining_coverage <= _EPS:
                break
            capacity_risk_share = candidate.capacity_risk_share
            if capacity_risk_share <= _EPS:
                continue
            allocated_risk_share = min(
                capacity_risk_share,
                remaining_coverage / candidate.payoff_at_attachment,
            )
            if remaining_carry is not None:
                allocated_risk_share = min(
                    allocated_risk_share,
                    remaining_carry / candidate.annual_carry,
                )
            if allocated_risk_share <= _EPS:
                continue
            allocations[candidate.sleeve] = allocated_risk_share
            remaining_coverage -= allocated_risk_share * candidate.payoff_at_attachment
            if remaining_carry is not None:
                remaining_carry -= allocated_risk_share * candidate.annual_carry
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
        if (
            not math.isfinite(self.sleeve_reversion_fraction)
            or self.sleeve_reversion_fraction <= 0
            or self.sleeve_reversion_fraction > 1
        ):
            raise ValueError("sleeve_reversion_fraction must be in (0, 1]")
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
        overridden by the slow-reviewed convexity-premium budget when supplied.
        Expansion sleeves consume zero risk by default until a later slice gives
        them an explicit budget.
        """
        shares: dict[SleeveName, float] = {}
        for sleeve in self.sleeves:
            if sleeve.group == RiskGroup.EXPANSION:
                shares[sleeve.name] = 0.0
            else:
                shares[sleeve.name] = sleeve.risk_share
        if self.tail_convexity_budget is None:
            return shares

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
        sleeve_by_name = {sleeve.name: sleeve for sleeve in self.sleeves}
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

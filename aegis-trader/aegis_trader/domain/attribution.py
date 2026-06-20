"""Per-sleeve P&L attribution — reconciles to book P&L by construction.

Not a second ledger.  The book's realized gain over a period is the
realized-weight return identity

    P&L_book = Σ_i realized_w_{i,t-1} × return_{i,t} × NAV_{t-1}

where return_{i,t} = close_{i,t} / close_{i,t-1} - 1.  Each instrument's realized
weight is split across sleeves by their *budget-scaled target* share — the share
of the netted book position each sleeve intended.  Because the shares sum to 1
per instrument, the per-sleeve P&Ls sum back to the book P&L.  A position no
sleeve currently targets is split by budget fraction so reconciliation still
holds.  Pure domain — no Nautilus, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from aegis_runtime import InstrumentRef

from aegis_trader.domain.types import SleeveName

_EPS = 1e-15


@dataclass(frozen=True)
class AttributionPeriod:
    """One rebalance period's inputs for attribution.

    *realized_weights* — the book's realized weight (position/NAV) per FIGI, held
      into the next period; *sleeve_targets* — each sleeve's raw target weight per
      FIGI (pre-budget); *closes* — each FIGI's close; *nav* — book NAV.
    """

    nav: float
    realized_weights: Mapping[InstrumentRef, float]
    sleeve_targets: Mapping[SleeveName, Mapping[InstrumentRef, float]]
    closes: Mapping[InstrumentRef, float]


def compute_sleeve_attribution(
    periods: Sequence[AttributionPeriod],
    *,
    budgets: Mapping[SleeveName, float],
) -> dict[SleeveName, float]:
    """Per-sleeve P&L over *periods*, reconciling to book P&L.

    Returns a dict mapping each sleeve to its cumulative P&L in base currency.
    """
    result: dict[SleeveName, float] = {name: 0.0 for name in budgets}
    total_budget = sum(budgets.values())

    for prev, curr in zip(periods, periods[1:], strict=False):
        for figi, realized_w in prev.realized_weights.items():
            if abs(realized_w) < _EPS:
                continue
            prev_px = prev.closes.get(figi)
            curr_px = curr.closes.get(figi)
            if prev_px is None or curr_px is None or prev_px <= 0:
                continue
            book_contrib = realized_w * (curr_px / prev_px - 1.0) * prev.nav

            intended = {
                name: budgets[name] * prev.sleeve_targets.get(name, {}).get(figi, 0.0)
                for name in budgets
            }
            total_intended = sum(intended.values())
            for name in budgets:
                if abs(total_intended) > _EPS:
                    share = intended[name] / total_intended
                elif total_budget > _EPS:
                    share = budgets[name] / total_budget  # untargeted residual
                else:
                    share = 0.0
                result[name] += share * book_contrib

    return result

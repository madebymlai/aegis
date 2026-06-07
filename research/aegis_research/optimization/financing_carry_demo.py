"""Financing-carry ranking-bias demo (aegis-rd-kqg.10, original handoff Q7).

The justification gate the design session deferred: a *reproducible* carry-off vs
carry-on comparison on a representative market-neutral long/short grid that answers
whether short financing carry materially reorders the representative Candidates
(best/median/worst). If carry does not move the selection, that is the signal to stop
before building the rest of the financing-carry epic.

Carry is charged through the **settled mechanism** that will ship (ADR-0007 +
``docs/adr/0008-*``): a per-bar ``cash_dividends`` array masked to the short legs,
passed to ``Portfolio.from_optimizer`` — the same factory and the same charging path the
simulator uses. Here it serves only to *measure ranking sensitivity*, not to build the
production carry path (that is a later epic slice). Empirical fact #4 of the settled
design (a flat-price L/S book moving ``total_return 0 -> -0.02`` from carry alone) is what
makes a reorder plausible; this demo confirms it on a ranked grid.

The grid, ranking, and comparison are deterministic, so the result is reproducible: run
``compare_carry_ranking_bias()`` and read :class:`CarryRankingComparison`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
    select_representative_candidates,
)

SYMBOL_LEVEL = "symbol"
CANDIDATE_LEVEL = "candidate_id"
RANKING_METRIC = "total_return"

# Default short borrow carry rate the financing-carry design settled on (0.5%/yr net of
# rebate). The demo charges at this *shipping default* so the answer reflects what actually
# ships, not an inflated hard-to-borrow rate.
DEFAULT_SHORT_BORROW_RATE = 0.005
PERIODS_PER_YEAR = 252


@dataclass(frozen=True)
class CarryRankingComparison:
    """The carry-off vs carry-on representative-Candidate selection, side by side.

    ``carry_off_*`` / ``carry_on_*`` are the candidate identifiers selected for each role
    (best / median / worst) on the same grid, ranked by ``total_return``. ``reordered`` is
    ``True`` when any role's selection changed once short carry was charged — the
    justification-gate verdict: short financing carry *does* materially reorder the
    representative Candidates, so building the rest of the epic is warranted.
    """

    carry_off_best: str
    carry_off_median: str
    carry_off_worst: str
    carry_on_best: str
    carry_on_median: str
    carry_on_worst: str
    short_borrow_rate: float

    @property
    def reordered(self) -> bool:
        return (
            self.carry_off_best != self.carry_on_best
            or self.carry_off_median != self.carry_on_median
            or self.carry_off_worst != self.carry_on_worst
        )

    def as_note(self) -> dict[str, Any]:
        """A structured, recordable verdict that justifies the build decision either way.

        Carries the carry-off vs carry-on representative-Candidate selection, the rate
        carry was charged at, the shipping mechanism it used, and the reorder verdict.
        """
        return {
            "verdict": "reordered" if self.reordered else "unchanged",
            "short_borrow_rate": self.short_borrow_rate,
            "mechanism": "cash_dividends_short_borrow",
            "carry_off": {
                "best": self.carry_off_best,
                "median": self.carry_off_median,
                "worst": self.carry_off_worst,
            },
            "carry_on": {
                "best": self.carry_on_best,
                "median": self.carry_on_median,
                "worst": self.carry_on_worst,
            },
        }


def compare_carry_ranking_bias(
    short_borrow_rate: float = DEFAULT_SHORT_BORROW_RATE,
) -> CarryRankingComparison:
    """Run a representative L/S grid carry-off vs carry-on and compare the selection.

    The same market-neutral grid is simulated twice through ``Portfolio.from_optimizer``:
    once with no carry, once with short borrow carry charged via a short-masked
    ``cash_dividends`` array. Each run's per-Candidate ``total_return`` feeds the existing
    global ranking (:func:`select_representative_candidates`), and the best/median/worst
    selections are returned side by side.
    """
    close, allocations = _market_neutral_grid()
    pfo = _filled_optimizer(allocations)

    off_result = _rank_run(close, pfo, cash_dividends=None)
    on_result = _rank_run(
        close,
        pfo,
        cash_dividends=short_masked_cash_dividends(
            close, allocations, short_borrow_rate
        ),
    )
    return CarryRankingComparison(
        carry_off_best=_candidate_id(off_result.best),
        carry_off_median=_candidate_id(off_result.median),
        carry_off_worst=_candidate_id(off_result.worst),
        carry_on_best=_candidate_id(on_result.best),
        carry_on_median=_candidate_id(on_result.median),
        carry_on_worst=_candidate_id(on_result.worst),
        short_borrow_rate=short_borrow_rate,
    )


def _market_neutral_grid() -> tuple[pd.DataFrame, pd.DataFrame]:
    """A representative market-neutral L/S grid: candidates differ only in short notional.

    Two symbols with a tiny opposing price drift (long A / short B earns a small gross edge
    that scales with book size, so the heaviest-short Candidate is the *pre-carry* winner).
    Three Candidates hold a fully signed long/short pair at different gross levels — all
    market-neutral (net ~0), all below the gross-leverage ceiling. Short carry, falling
    hardest on the heaviest short, is what can re-sort them.
    """
    periods = 504
    index = pd.date_range("2022-01-01", periods=periods, freq="D")
    # A drifts up a hair, B down a hair: a long-A/short-B edge that grows with book size.
    close_a = np.linspace(100.0, 100.08, periods)
    close_b = np.linspace(100.0, 99.92, periods)
    symbol_series = {"A": close_a, "B": close_b}

    weights = {
        "light_short": (0.4, -0.4),
        "mid_short": (0.6, -0.6),
        "heavy_short": (0.9, -0.9),
    }
    columns = pd.MultiIndex.from_product(
        [list(weights), ["A", "B"]], names=[CANDIDATE_LEVEL, SYMBOL_LEVEL]
    )
    close = pd.DataFrame(
        {column: symbol_series[column[1]] for column in columns}, index=index
    )
    close.columns = columns

    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    for candidate, (weight_a, weight_b) in weights.items():
        allocations.loc[index[0], (candidate, "A")] = weight_a
        allocations.loc[index[0], (candidate, "B")] = weight_b
    return close, allocations


def _filled_optimizer(allocations: pd.DataFrame) -> vbt.PFO:
    return vbt.PFO.from_filled_allocations(
        allocations.ffill(),
        valid_only=True,
        nonzero_only=False,
        unique_only=False,
    )


def short_masked_cash_dividends(
    close: pd.DataFrame, allocations: pd.DataFrame, short_borrow_rate: float
) -> pd.DataFrame:
    """The settled carry mechanism: ``rate_per_bar * close``, masked to short legs.

    A positive per-share ``cash_dividends`` is a *cost* on a short position and a credit on
    a long one (position-sign dependent), so long legs are masked to ``0`` — only the short
    legs are charged. ``rate * close * live position`` gives the drifted short-notional
    carry for free, charged only while the short is open.
    """
    rate_per_bar = short_borrow_rate / PERIODS_PER_YEAR
    short_mask = allocations.ffill() < 0
    cash_dividends = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    cash_dividends[short_mask] = rate_per_bar * close[short_mask]
    return cash_dividends


def _rank_run(
    close: pd.DataFrame,
    pfo: vbt.PFO,
    *,
    cash_dividends: pd.DataFrame | None,
) -> OptimizationResult:
    pf = vbt.Portfolio.from_optimizer(
        close,
        pfo,
        pf_method="from_orders",
        size_type="targetpercent",
        direction="both",
        cash_sharing=True,
        call_seq="auto",
        group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
        fees=0,
        slippage=0,
        init_cash=10_000.0,
        leverage=2.0,
        leverage_mode="eager",
        cash_dividends=cash_dividends,
    )
    grid = _ranking_grid(pf.get_total_return())
    return select_representative_candidates(grid, metric=RANKING_METRIC)


def _ranking_grid(total_return: pd.Series) -> pd.DataFrame:
    """One row per (candidate, split) — a single demo split — carrying ``total_return``."""
    candidate_ids = list(total_return.index)
    index = pd.MultiIndex.from_tuples(
        [("demo", candidate_id) for candidate_id in candidate_ids],
        names=["split", CANDIDATE_LEVEL],
    )
    return pd.DataFrame(
        {RANKING_METRIC: total_return.to_numpy(dtype=float)}, index=index
    )


def _candidate_id(candidate: EvaluatedCandidate) -> str:
    return str(candidate.params[CANDIDATE_LEVEL])

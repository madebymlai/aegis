"""Nautilus cost models for the backtest Trader venue.

Domain cost parameters stay in ``domain.book_config.CostModelConfig``.  This
module is the Nautilus-layer adapter that turns them into models accepted by the
backtest matching engine.  Paper/live take broker-reported costs, not these
(aegis-rd-fuu.9).
"""

from __future__ import annotations

from dataclasses import dataclass

from nautilus_trader.backtest.models import FeeModel, FillModel
from nautilus_trader.model.objects import Money

from aegis_trader.domain.book_config import BookConfig, CostModelConfig


def build_simulated_fill_model(costs: CostModelConfig) -> FillModel:
    """Return the Nautilus fill model for simulated venues.

    Limit fills stay deterministic (``prob_fill_on_limit=1.0``); the only
    stochastic knob is the configured one-tick slippage, seeded for
    reproducible runs.
    """
    return FillModel(
        prob_fill_on_limit=1.0,
        prob_slippage=costs.slippage_probability,
        random_seed=costs.slippage_seed,
    )


@dataclass(frozen=True)
class SimulatedCostModels:
    """The two Nautilus models injected into a simulated venue."""

    fee_model: FeeModel
    fill_model: FillModel


def build_simulated_cost_models(book: BookConfig) -> SimulatedCostModels:
    """Derive simulated venue cost models from the Book Config."""
    return SimulatedCostModels(
        fee_model=IbkrEquityFeeModel(book.costs),
        fill_model=build_simulated_fill_model(book.costs),
    )


class IbkrEquityFeeModel(FeeModel):
    """Currency-agnostic IBKR equity commission, per-share or per-value.

    The variable charge is ``per_share_commission`` per share (IBKR US pricing) plus
    ``commission_pct`` of notional (IBKR Europe pricing); a venue sets the basis it
    uses and leaves the other at zero. That variable is floored at
    ``min_commission_per_order`` (the per-order minimum, e.g. EUR 1.25) and, when
    ``max_commission_pct`` is set, capped at that fraction of notional — the full
    IBKR ``min(max(floor, variable), cap)`` shape.
    """

    def __init__(self, costs: CostModelConfig) -> None:
        self._costs = costs

    def get_commission(self, order, fill_qty, fill_px, instrument) -> Money:
        quantity = abs(fill_qty.as_double())
        notional = abs(instrument.notional_value(
            quantity=fill_qty,
            price=fill_px,
            use_quote_for_inverse=False,
        ).as_double())
        variable = (
            self._costs.per_share_commission * quantity
            + self._costs.commission_pct * notional
        )
        base_commission = max(self._costs.min_commission_per_order, variable)
        if self._costs.max_commission_pct > 0.0:
            base_commission = min(
                base_commission,
                self._costs.max_commission_pct * notional,
            )
        return Money(base_commission, instrument.quote_currency)

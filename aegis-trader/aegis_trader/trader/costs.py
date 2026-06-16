"""Nautilus cost models for simulated Trader venues.

Domain cost parameters stay in ``domain.book_config.CostModelConfig``.  This
module is the Nautilus-layer adapter that turns them into models accepted by the
backtest and sandbox matching engines.
"""

from __future__ import annotations

from dataclasses import dataclass

from nautilus_trader.backtest.models import FeeModel, FillModel
from nautilus_trader.model.objects import Money

from aegis_trader.domain.book_config import BookConfig, CostModelConfig


class SimulatedFillModel(FillModel):
    """FillModel retaining the configured seed for deterministic-run evidence."""

    def __init__(self, costs: CostModelConfig) -> None:
        super().__init__(
            prob_fill_on_limit=1.0,
            prob_slippage=costs.slippage_probability,
            random_seed=costs.slippage_seed,
        )
        self.random_seed = costs.slippage_seed


def build_simulated_fill_model(costs: CostModelConfig) -> SimulatedFillModel:
    """Return the Nautilus fill model for simulated venues."""
    return SimulatedFillModel(costs)


@dataclass(frozen=True)
class SimulatedCostModels:
    """The two Nautilus models injected into a simulated venue."""

    fee_model: FeeModel
    fill_model: FillModel


def build_simulated_cost_models(book: BookConfig) -> SimulatedCostModels:
    """Derive simulated venue cost models from the Book Config."""
    return SimulatedCostModels(
        fee_model=IbkrPerShareFeeModel(book.costs),
        fill_model=build_simulated_fill_model(book.costs),
    )


class IbkrPerShareFeeModel(FeeModel):
    """Currency-agnostic IBKR-style equity commission."""

    def __init__(self, costs: CostModelConfig) -> None:
        self._costs = costs

    def get_commission(self, order, fill_qty, fill_px, instrument) -> Money:
        quantity = abs(fill_qty.as_double())
        notional = abs(instrument.notional_value(
            quantity=fill_qty,
            price=fill_px,
            use_quote_for_inverse=False,
        ).as_double())
        per_share = self._costs.per_share_commission * quantity
        base_commission = max(self._costs.min_commission_per_order, per_share)
        if self._costs.max_commission_pct > 0.0:
            base_commission = min(
                base_commission,
                self._costs.max_commission_pct * notional,
            )
        return Money(base_commission, instrument.quote_currency)

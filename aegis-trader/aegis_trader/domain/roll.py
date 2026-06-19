from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

from aegis_trader.domain.types import OrderIntent, OrderSide, OrderSource, ResolvedContractId


@dataclass(frozen=True)
class HeldContract:
    """A reconciled held contract folded to its canonical InstrumentRef."""

    ref: InstrumentRef
    contract_id: ResolvedContractId
    quantity: float


AsOfResolver = Callable[[InstrumentRef, date], ResolvedContractId]


def roll_positions(
    held: tuple[HeldContract, ...],
    *,
    as_of: date,
    resolve: AsOfResolver,
) -> tuple[OrderIntent, ...]:
    """Emit mandatory exposure-neutral roll orders for stale futures contracts.

    ListedRefs never roll. A FuturesRef rolls only when the currently held dated
    contract differs from the contract resolved for ``as_of``. The emitted pair
    is labelled ``ROLL`` so the Strategy can log and submit it distinctly from
    alpha drift orders; drift bands never participate in this pure step.
    """
    orders: list[OrderIntent] = []
    for position in held:
        if isinstance(position.ref, ListedRef):
            continue
        if not isinstance(position.ref, FuturesRef):
            raise ValueError(f"unsupported InstrumentRef variant {type(position.ref).__name__}")
        current = resolve(position.ref, as_of)
        if current == position.contract_id:
            continue
        quantity = abs(position.quantity)
        if quantity == 0.0:
            continue
        exit_side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
        enter_side = OrderSide.BUY if position.quantity > 0 else OrderSide.SELL
        orders.append(
            OrderIntent(
                ref=position.ref,
                side=exit_side,
                quantity=quantity,
                source=OrderSource.ROLL,
                resolved_contract_id=position.contract_id,
            )
        )
        orders.append(
            OrderIntent(
                ref=position.ref,
                side=enter_side,
                quantity=quantity,
                source=OrderSource.ROLL,
                resolved_contract_id=current,
            )
        )
    return tuple(orders)

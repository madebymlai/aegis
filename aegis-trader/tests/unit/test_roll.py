from __future__ import annotations

from datetime import date

from aegis_runtime import FuturesRef, ListedRef
from aegis_trader.domain.roll import HeldContract, roll_positions
from aegis_trader.domain.types import OrderSide, OrderSource, ResolvedContractId


def test_listed_ref_never_rolls() -> None:
    ref = ListedRef("BBG000B9XRY4")
    held = HeldContract(ref=ref, contract_id=ResolvedContractId("VUSA.XLON"), quantity=10.0)

    orders = roll_positions((held,), as_of=date(2024, 12, 15), resolve=lambda _ref, _as_of: ResolvedContractId("VUSA.XLON"))

    assert orders == ()


def test_future_roll_emits_exposure_neutral_pair() -> None:
    ref = FuturesRef(root="ES", dataset="cme")
    held = HeldContract(ref=ref, contract_id=ResolvedContractId("ESZ4.XCME"), quantity=3.0)

    orders = roll_positions((held,), as_of=date(2024, 12, 15), resolve=lambda _ref, _as_of: ResolvedContractId("ESH5.XCME"))

    assert len(orders) == 2
    assert orders[0].ref == ref
    assert orders[0].resolved_contract_id == ResolvedContractId("ESZ4.XCME")
    assert orders[0].side == OrderSide.SELL
    assert orders[0].quantity == 3.0
    assert orders[0].source == OrderSource.ROLL
    assert orders[1].resolved_contract_id == ResolvedContractId("ESH5.XCME")
    assert orders[1].side == OrderSide.BUY
    assert orders[1].quantity == 3.0
    assert orders[1].source == OrderSource.ROLL


def test_future_roll_is_idempotent_when_held_contract_is_current() -> None:
    ref = FuturesRef(root="ES", dataset="cme")
    held = HeldContract(ref=ref, contract_id=ResolvedContractId("ESH5.XCME"), quantity=3.0)

    orders = roll_positions((held,), as_of=date(2024, 12, 15), resolve=lambda _ref, _as_of: ResolvedContractId("ESH5.XCME"))

    assert orders == ()

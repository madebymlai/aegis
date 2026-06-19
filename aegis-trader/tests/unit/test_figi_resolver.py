from __future__ import annotations

from datetime import date

import pytest
from aegis_runtime import FuturesRef, ListedRef
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.execution.figi_resolver import (
    FigiInstrumentResolver,
    FigiResolutionError,
    FuturesContract,
)


def test_futures_ref_resolves_as_of_and_records_inverse():
    ref = FuturesRef(root="ES", dataset="cme", roll_rule="calendar", adjustment="unadjusted")

    def calendar(futures_ref: FuturesRef, as_of: date) -> FuturesContract:
        assert futures_ref == ref
        symbol = "ESZ4" if as_of < date(2024, 12, 15) else "ESH5"
        return FuturesContract(symbol=symbol, exchange="GLBX")

    def contract_resolver(contract: FuturesContract) -> InstrumentId:
        assert contract.exchange == "GLBX"
        return InstrumentId.from_str(f"{contract.symbol}.XCME")

    resolver = FigiInstrumentResolver(
        futures_calendar=calendar,
        futures_contract_resolver=contract_resolver,
    )

    before_roll = resolver.resolve(ref, as_of=date(2024, 12, 14))
    after_roll = resolver.resolve(ref, as_of=date(2024, 12, 15))

    assert before_roll == InstrumentId.from_str("ESZ4.XCME")
    assert after_roll == InstrumentId.from_str("ESH5.XCME")
    assert resolver.ref_for(InstrumentId.from_str("ESH5.XCME")) == ref


def test_futures_ref_requires_as_of():
    resolver = FigiInstrumentResolver(
        futures_calendar=lambda ref, as_of: FuturesContract(symbol="ESZ4", exchange="GLBX"),
        futures_contract_resolver=lambda contract: InstrumentId.from_str("ESZ4.XCME"),
    )

    with pytest.raises(FigiResolutionError, match="as_of is required"):
        resolver.resolve(FuturesRef(root="ES", dataset="cme"))


def test_listed_ref_is_not_resolved_by_figi_resolver():
    resolver = FigiInstrumentResolver()

    with pytest.raises(FigiResolutionError, match="IB InstrumentProvider"):
        resolver.resolve(ListedRef("BBG000R20GS9"), as_of=date(2024, 1, 1))


def test_resolve_many_is_empty_only_until_resolver_husk_is_deleted():
    resolver = FigiInstrumentResolver()

    assert resolver.resolve_many(set()) == {}
    with pytest.raises(FigiResolutionError, match="batch ListedRef resolution"):
        resolver.resolve_many({ListedRef("BBG000R20GS9")})


def test_ref_for_unknown_contract_fails_closed():
    resolver = FigiInstrumentResolver()

    with pytest.raises(FigiResolutionError, match="no resolved InstrumentRef inverse"):
        resolver.ref_for(InstrumentId.from_str("ESZ4.XCME"))

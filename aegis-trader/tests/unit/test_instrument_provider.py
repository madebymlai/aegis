from __future__ import annotations

from dataclasses import dataclass

import pytest
from aegis_runtime import ListedRef
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.execution.figi_resolver import FigiResolutionError
from aegis_trader.trader.instrument_provider import (
    IB_LISTED_MIC_OVERRIDES,
    declared_ref_currencies,
    listed_ref_ib_contracts,
    loaded_listed_ref_bimap,
    reconcile_quote_currency,
)


@dataclass(frozen=True)
class _Instrument:
    id: InstrumentId
    info: dict


def _loaded_equity(figi: str, instrument_id: str) -> _Instrument:
    return _Instrument(
        id=InstrumentId.from_str(instrument_id),
        info={"contract": {"secIdType": "FIGI", "secId": figi}},
    )


@dataclass(frozen=True)
class _Contract:
    refs: tuple[ListedRef, ...]


@dataclass(frozen=True)
class _Bundle:
    contract: _Contract
    symbols: tuple[str, ...]
    currency_by_symbol: dict[str, str]


def test_listed_ref_ib_contracts_request_figis_through_smart_stock_contracts():
    refs = {ListedRef("BBG000B9XRY4"), ListedRef("BBG000R20GS9")}

    contracts = listed_ref_ib_contracts(refs)

    assert contracts == [
        {
            "secType": "STK",
            "secIdType": "FIGI",
            "secId": "BBG000B9XRY4",
            "exchange": "SMART",
        },
        {
            "secType": "STK",
            "secIdType": "FIGI",
            "secId": "BBG000R20GS9",
            "exchange": "SMART",
        },
    ]


def test_listed_ref_mic_override_maps_igln_to_london_mic():
    assert IB_LISTED_MIC_OVERRIDES == {"IGLN": "XLON"}


def test_loaded_listed_ref_bimap_records_provider_returned_instrument_id():
    ref = ListedRef("BBG000R20GS9")
    instruments = [_loaded_equity(ref.figi, "GBUS.XLON")]

    bimap = loaded_listed_ref_bimap({ref}, instruments)

    assert bimap == {ref: InstrumentId.from_str("GBUS.XLON")}


def test_loaded_listed_ref_bimap_fails_closed_when_provider_did_not_load_ref():
    ref = ListedRef("BBG000R20GS9")

    with pytest.raises(FigiResolutionError, match="not loaded by the IB InstrumentProvider"):
        loaded_listed_ref_bimap({ref}, [])


def test_loaded_listed_ref_bimap_fails_closed_on_duplicate_figi_loads():
    ref = ListedRef("BBG000R20GS9")
    instruments = [
        _loaded_equity(ref.figi, "GBUS.XLON"),
        _loaded_equity(ref.figi, "GBUS.LSEETF"),
    ]

    with pytest.raises(FigiResolutionError, match="loaded more than once"):
        loaded_listed_ref_bimap({ref}, instruments)


def test_reconcile_quote_currency_keeps_declared_pence_when_ib_reports_major_gbp():
    ref = ListedRef("BBG000R20GS9")

    currency = reconcile_quote_currency(ref, "GBP", {ref: "GBp"})

    assert currency == "GBp"


def test_reconcile_quote_currency_fails_closed_on_real_currency_disagreement():
    ref = ListedRef("BBG000R20GS9")

    with pytest.raises(FigiResolutionError, match="disagrees"):
        reconcile_quote_currency(ref, "USD", {ref: "GBp"})


def test_declared_ref_currencies_reads_bundle_plan_currencies_by_ref():
    ref = ListedRef("BBG000R20GS9")
    bundle = _Bundle(
        contract=_Contract(refs=(ref,)),
        symbols=("GBUS.L",),
        currency_by_symbol={"GBUS.L": "GBp"},
    )

    currencies = declared_ref_currencies([bundle])

    assert currencies == {ref: "GBp"}

"""Shared bare continuous-future root validation (r8b.9 Slice A).

A continuous-future root is a *bare* symbol (``ES``), not a venue-qualified native id
(``ES.XCME`` — that is the materialised continuous-root ``InstrumentId``, built downstream by
aegis-data; the venue is catalog-authoritative).  Research (``DataConfig.futures``) and live
(``DataContract.futures``) both carry roots as plain strings and validate them with this one
function, so a venue-qualified id is rejected identically on both sides.
"""

from __future__ import annotations

import pytest

from aegis_runtime import DataContract, validate_bare_root
from nautilus_trader.model.identifiers import InstrumentId

_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_ES = InstrumentId.from_str("ES.XCME")
_KC = InstrumentId.from_str("KC.XNYM")


def _contract(
    *,
    futures: tuple[str, ...],
    instrument_ids: tuple[InstrumentId, ...] = (_AAPL,),
) -> DataContract:
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        lookback_bars=1,
        futures=futures,
    )


def test_bare_root_symbol_is_accepted_and_returned() -> None:
    assert validate_bare_root("ES") == "ES"
    assert validate_bare_root("6E") == "6E"


def test_venue_qualified_native_id_is_rejected() -> None:
    # It parses as an InstrumentId (symbol.venue), so it is an id, not a bare root.
    with pytest.raises(ValueError, match="bare root"):
        validate_bare_root("ES.XCME")


def test_empty_root_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_bare_root("")


@pytest.mark.parametrize("garbage", ["ES.", ".", "ES..XCME", "ES XCME", "ES ", " ES", "ES/", "ES.X"])
def test_malformed_or_whitespaced_root_is_rejected(garbage: str) -> None:
    # A config typo must fail here, not later when aegis-data builds Symbol(root).
    with pytest.raises(ValueError, match="bare root"):
        validate_bare_root(garbage)


def test_data_contract_defaults_to_no_futures() -> None:
    contract = DataContract(
        instrument_ids=(_AAPL,), required_arrays=("Close",), base_currency="EUR", timeframe="1D"
    )
    assert contract.futures == ()


def test_data_contract_accepts_bare_roots() -> None:
    contract = _contract(futures=("ES", "KC"), instrument_ids=(_AAPL, _ES, _KC))

    assert contract.futures == ("ES", "KC")


def test_data_contract_rejects_root_without_matching_continuous_id() -> None:
    with pytest.raises(ValueError, match="no matching instrument_id"):
        _contract(futures=("ES",))


def test_data_contract_rejects_ambiguous_matching_continuous_id() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        _contract(
            futures=("ES",),
            instrument_ids=(_ES, InstrumentId.from_str("ES.NASDAQ")),
        )


def test_data_contract_rejects_venue_qualified_root() -> None:
    with pytest.raises(ValueError, match="bare root"):
        _contract(futures=("ES.XCME",))


def test_data_contract_rejects_duplicate_roots() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _contract(futures=("ES", "ES"))

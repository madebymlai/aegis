"""Shared bare continuous-future root validation (r8b.9 Slice A).

A continuous-future root is a *bare* symbol (``ES``), not a venue-qualified native id
(``ES.XCME`` — that is the materialised continuous-root ``InstrumentId``, built downstream by
aegis-data; the venue is catalog-authoritative).  Research (``DataConfig.futures``) and live
(``DataContract.futures``) both carry roots as plain strings and validate them with this one
function, so a venue-qualified id is rejected identically on both sides.
"""

from __future__ import annotations

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    DataContract,
    DataContractError,
    MissingIndexPolicy,
    validate_bare_root,
)

_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_ES = InstrumentId.from_str("ES.XCME")
_KC = InstrumentId.from_str("KC.XNYM")
_EURUSD = InstrumentId.from_str("EUR/USD.IDEALPRO")


def _contract(
    *,
    futures: tuple[str, ...],
    instrument_ids: tuple[InstrumentId, ...] = (_AAPL,),
    adjustment_mode: ContinuousFutureAdjustmentType | None = None,
    exchange: tuple[InstrumentId, ...] = (),
) -> DataContract:
    if futures and adjustment_mode is None:
        adjustment_mode = ContinuousFutureAdjustmentType.BACKWARD_RATIO
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=1,
        futures=futures,
        exchange=exchange,
        adjustment_mode=adjustment_mode,
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


@pytest.mark.parametrize(
    "garbage", ["ES.", ".", "ES..XCME", "ES XCME", "ES ", " ES", "ES/", "ES.X"]
)
def test_malformed_or_whitespaced_root_is_rejected(garbage: str) -> None:
    # A config typo must fail here, not later when aegis-data builds Symbol(root).
    with pytest.raises(ValueError, match="bare root"):
        validate_bare_root(garbage)


def test_data_contract_defaults_to_no_futures() -> None:
    contract = DataContract(
        instrument_ids=(_AAPL,),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
    )
    assert contract.futures == ()


def test_data_contract_accepts_bare_roots() -> None:
    contract = _contract(futures=("ES", "KC"), instrument_ids=(_AAPL, _ES, _KC))

    assert contract.futures == ("ES", "KC")


def test_data_contract_returns_declared_continuous_instrument_ids() -> None:
    contract = _contract(futures=("ES", "KC"), instrument_ids=(_AAPL, _ES, _KC))

    assert contract.continuous_instrument_ids == (_ES, _KC)
    assert contract.native_instrument_ids == (_AAPL,)


@pytest.mark.parametrize(
    ("futures", "instrument_ids", "exchange", "expected_continuous", "expected_native"),
    [
        ((), (_AAPL,), (), (), (_AAPL,)),
        (("ES",), (_AAPL, _ES), (), (_ES,), (_AAPL,)),
        (("ES", "KC"), (_ES, _AAPL, _KC), (), (_ES, _KC), (_AAPL,)),
        ((), (_AAPL,), (_EURUSD,), (), (_AAPL,)),
        (("ES",), (_ES, _AAPL), (_EURUSD,), (_ES,), (_AAPL,)),
    ],
)
def test_native_and_continuous_ids_partition_the_declared_universe(
    futures: tuple[str, ...],
    instrument_ids: tuple[InstrumentId, ...],
    exchange: tuple[InstrumentId, ...],
    expected_continuous: tuple[InstrumentId, ...],
    expected_native: tuple[InstrumentId, ...],
) -> None:
    """`native` and `continuous` partition `instrument_ids` — nothing else is a target.

    Each row's two expectations reconstitute that row's `instrument_ids` exactly,
    and an `exchange` leg appears in neither: data-only legs are kept out of the
    declared universe by the no-overlap rule, not by the partition. This is what
    lets a caller take `instrument_ids` as the rebalance-target set instead of
    re-deriving one.
    """
    contract = _contract(
        futures=futures, instrument_ids=instrument_ids, exchange=exchange
    )

    assert contract.continuous_instrument_ids == expected_continuous
    assert contract.native_instrument_ids == expected_native


def test_data_contract_continuous_identity_agrees_across_sleeves() -> None:
    trend = _contract(futures=("ES",), instrument_ids=(_AAPL, _ES))
    carry = _contract(futures=("ES",), instrument_ids=(_ES,))

    assert trend.continuous_instrument_ids == (_ES,)
    assert carry.continuous_instrument_ids == (_ES,)


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


# --- adjustment mode: present iff futures, backward-only, independent of FX ------


@pytest.mark.parametrize(
    "mode",
    [
        ContinuousFutureAdjustmentType.BACKWARD_RATIO,
        ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    ],
)
@pytest.mark.parametrize("exchange", [(), (_EURUSD,)])
def test_data_contract_accepts_both_backward_modes_with_and_without_fx(
    mode: ContinuousFutureAdjustmentType, exchange: tuple[InstrumentId, ...]
) -> None:
    # Adjustment mode and ``exchange`` are independent declarations: ratio and
    # spread are both valid whether or not FX conversion legs exist.
    contract = _contract(
        futures=("ES",),
        instrument_ids=(_AAPL, _ES),
        adjustment_mode=mode,
        exchange=exchange,
    )

    assert contract.adjustment_mode is mode
    assert contract.exchange == exchange


def test_data_contract_rejects_futures_without_adjustment_mode() -> None:
    with pytest.raises(DataContractError, match="no adjustment_mode"):
        DataContract(
            instrument_ids=(_AAPL, _ES),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            futures=("ES",),
        )


def test_data_contract_rejects_adjustment_mode_without_futures() -> None:
    with pytest.raises(DataContractError, match="futures declares no"):
        _contract(
            futures=(),
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
        )


@pytest.mark.parametrize("bad_mode", ["backward_ratio", 2, object()])
def test_data_contract_rejects_non_enum_adjustment_mode(bad_mode) -> None:
    # The contract carries the native Nautilus enum, never a string or a
    # parallel Aegis encoding.
    with pytest.raises(DataContractError, match="ContinuousFutureAdjustmentType"):
        _contract(
            futures=("ES",),
            instrument_ids=(_AAPL, _ES),
            adjustment_mode=bad_mode,
        )


@pytest.mark.parametrize(
    "forward_mode",
    [
        ContinuousFutureAdjustmentType.FORWARD_RATIO,
        ContinuousFutureAdjustmentType.FORWARD_SPREAD,
    ],
)
def test_data_contract_rejects_forward_adjustment_modes(
    forward_mode: ContinuousFutureAdjustmentType,
) -> None:
    with pytest.raises(DataContractError, match="unsupported"):
        _contract(
            futures=("ES",),
            instrument_ids=(_AAPL, _ES),
            adjustment_mode=forward_mode,
        )

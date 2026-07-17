from __future__ import annotations

from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    DataContract,
    DriftBand,
    ExecutionBundle,
    MissingIndexPolicy,
)

from tests.support.factories import make_bundle

_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_ES = InstrumentId.from_str("ES.XCME")
_EURUSD = InstrumentId.from_str("EUR/USD.IDEALPRO")
_MSFT = InstrumentId.from_str("MSFT.NASDAQ")


def test_make_bundle_requires_no_arguments() -> None:
    bundle = make_bundle()

    assert isinstance(bundle, ExecutionBundle)


def test_make_bundle_supplies_a_default_contract() -> None:
    bundle = make_bundle()

    assert bundle.contract == DataContract(
        instrument_ids=(_AAPL,),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=20,
    )


def test_make_bundle_supplies_a_default_band() -> None:
    bundle = make_bundle()

    assert bundle.instrument_bands == {_AAPL: DriftBand.symmetric(0.0)}


def test_make_bundle_supplies_a_default_direction() -> None:
    bundle = make_bundle()

    assert bundle.direction == "both"


def test_make_bundle_applies_contract_overrides() -> None:
    bundle = make_bundle(
        timeframe="1H",
        native_instrument_ids=(_MSFT,),
        exchange_instrument_ids=(_EURUSD,),
        continuous_futures={"ES": _ES},
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
        lookback_bars=99,
    )

    assert bundle.contract == DataContract(
        instrument_ids=(_MSFT, _ES),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1H",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=99,
        futures=("ES",),
        exchange=(_EURUSD,),
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    )


def test_make_bundle_applies_band_overrides() -> None:
    msft_band = DriftBand(up=0.10, down=0.20)

    bundle = make_bundle(
        native_instrument_ids=(_MSFT,),
        instrument_bands={_MSFT: msft_band},
    )

    assert bundle.instrument_bands == {_MSFT: msft_band}


def test_make_bundle_applies_direction_override() -> None:
    bundle = make_bundle(direction="shortonly")

    assert bundle.direction == "shortonly"

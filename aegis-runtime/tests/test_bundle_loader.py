import json
import sys

import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    LockedExecutionPlan,
    MissingIndexPolicy,
)
from aegis_runtime.bundle_loader import (
    BUNDLE_PAYLOAD_SCHEMA_VERSION,
    BundlePayloadFieldError,
    BundlePayloadSchemaError,
    dump_bundle_payload,
    load_bundle_payload,
    load_installed_bundle,
)
from aegis_runtime.drift_band import DriftBand


def _contract() -> DataContract:
    return DataContract(
        instrument_ids=(_id("AAPL.NASDAQ"), _id("ESZ6.XCME")),
        required_arrays=("Close", "Open"),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=20,
    )


def _manifest(contract: DataContract) -> BundleManifest:
    return BundleManifest(
        run_id="run-1",
        role="best",
        candidate_key="0123456789abcdef",
        component_source_hashes={"strategies/test": "abc123"},
        instrument_ids=contract.instrument_ids,
    )


def _plan(instrument_ids: tuple[InstrumentId, ...] | None = None) -> LockedExecutionPlan:
    if instrument_ids is None:
        instrument_ids = _contract().instrument_ids
    strategy = ComponentSpec(
        family="strategies",
        component_id="tests.strategy",
        module="bundle.strategy",
        input_names=("Close",),
        output_names=("target_weights",),
        params={"window": 5},
    )
    indicator = ComponentSpec(
        family="indicators",
        component_id="tests.indicator",
        module="bundle.indicator_0",
        input_names=("Close",),
        output_names=("score",),
        params={"half_life": 3},
    )
    return LockedExecutionPlan(
        strategy=strategy,
        indicators=(indicator,),
        instrument_bands={
            instrument_id: DriftBand(up=0.10, down=0.20) for instrument_id in instrument_ids
        },
        gross_cap=1.0,
        net_cap=None,
        direction="longonly",
    )


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def test_bundle_payload_round_trips_native_instrument_ids() -> None:
    contract = _contract()
    plan = _plan(contract.instrument_ids)

    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=plan,
    )
    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    assert payload["schema_version"] == BUNDLE_PAYLOAD_SCHEMA_VERSION
    assert payload["contract"]["instrument_ids"] == ["AAPL.NASDAQ", "ESZ6.XCME"]
    assert payload["contract"]["missing_index"] == "drop"
    assert payload["plan"]["instrument_bands"] == {
        "AAPL.NASDAQ": {"up": 0.10, "down": 0.20, "destination_fraction": 1.0},
        "ESZ6.XCME": {"up": 0.10, "down": 0.20, "destination_fraction": 1.0},
    }
    assert bundle.contract == contract
    assert bundle.manifest == _manifest(contract)
    assert bundle.instrument_bands == plan.instrument_bands
    assert bundle.gross_cap == plan.gross_cap
    assert bundle.net_cap == plan.net_cap


def test_bundle_payload_round_trips_band_destination_fraction() -> None:
    contract = _contract()
    plan = _plan(contract.instrument_ids)
    banded = LockedExecutionPlan(
        strategy=plan.strategy,
        indicators=plan.indicators,
        instrument_bands={
            instrument_id: DriftBand(up=0.10, down=0.20, destination_fraction=0.5)
            for instrument_id in contract.instrument_ids
        },
        gross_cap=plan.gross_cap,
        net_cap=plan.net_cap,
        direction=plan.direction,
    )

    payload = dump_bundle_payload(contract=contract, manifest=_manifest(contract), plan=banded)
    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    assert bundle.instrument_bands == banded.instrument_bands


def test_bundle_payload_without_destination_fraction_loads_trade_to_target() -> None:
    """Pre-destination bundles carry only widths; 1.0 is their exact behaviour."""
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    for band_payload in payload["plan"]["instrument_bands"].values():
        del band_payload["destination_fraction"]

    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    for band in bundle.instrument_bands.values():
        assert band.destination_fraction == 1.0


def test_bundle_payload_round_trips_continuous_future_roots() -> None:
    """The continuous-root declaration must survive the wheel payload, or the additive-
    invariance guard (which keys off ``contract.futures``) is dead on a loaded bundle."""
    contract = DataContract(
        instrument_ids=(_id("ES.XCME"),),
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=20,
        futures=("ES",),
    )

    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    assert payload["contract"]["futures"] == ["ES"]
    assert bundle.contract.futures == ("ES",)


def test_bundle_payload_round_trips_exchange_conversion_legs() -> None:
    """The contract's FX conversion legs (aegis-rd-reyj) survive dump→load."""
    contract = DataContract(
        instrument_ids=(_id("AAPL.NASDAQ"),),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=20,
        exchange=(_id("EUR/USD.IDEALPRO"),),
    )
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    assert payload["contract"]["exchange"] == ["EUR/USD.IDEALPRO"]
    assert bundle.contract.exchange == (_id("EUR/USD.IDEALPRO"),)


def test_bundle_payload_rejects_contract_without_exchange() -> None:
    """Pre-v3 wheels omit the conversion legs; they must fail loud, not load
    as a silently FX-less book (the aegis-rd-reyj tail-only failure mode)."""
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    del payload["contract"]["exchange"]

    with pytest.raises(BundlePayloadFieldError, match="exchange"):
        load_bundle_payload(payload)


def test_data_contract_rejects_exchange_overlapping_tradeables() -> None:
    """An id cannot be both a compute column and a conversion-only leg."""
    with pytest.raises(ValueError, match="exchange"):
        DataContract(
            instrument_ids=(_id("AAPL.NASDAQ"),),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            exchange=(_id("AAPL.NASDAQ"),),
        )


def test_bundle_payload_rejects_pre_v2_payload_without_schema_version() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    del payload["schema_version"]

    with pytest.raises(BundlePayloadSchemaError, match="schema_version"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_contract_without_missing_index_policy() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    del payload["contract"]["missing_index"]

    with pytest.raises(BundlePayloadFieldError, match="missing_index"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_contract_without_futures() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    del payload["contract"]["futures"]

    with pytest.raises(BundlePayloadFieldError, match="futures"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_future_root_without_matching_continuous_id() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(contract.instrument_ids),
    )
    payload["contract"]["instrument_ids"] = ["ESZ6.XCME"]
    payload["contract"]["futures"] = ["ES"]
    payload["manifest"]["instrument_ids"] = ["ESZ6.XCME"]
    payload["plan"]["instrument_bands"] = {
        "ESZ6.XCME": {"up": 0.10, "down": 0.20},
    }

    with pytest.raises(ValueError, match="no matching instrument_id"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_missing_instrument_ids() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(contract.instrument_ids),
    )
    del payload["contract"]["instrument_ids"]

    with pytest.raises(ValueError, match="instrument_ids"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_invalid_instrument_id() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(contract.instrument_ids),
    )
    payload["manifest"]["instrument_ids"][1] = ""

    with pytest.raises(ValueError, match="InstrumentId"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_missing_instrument_bands() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(contract.instrument_ids),
    )
    del payload["plan"]["instrument_bands"]

    with pytest.raises(ValueError, match="instrument_bands"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_instrument_band_contract_mismatch() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(contract.instrument_ids),
    )
    del payload["plan"]["instrument_bands"]["ESZ6.XCME"]
    payload["plan"]["instrument_bands"]["MSFT.NASDAQ"] = {"up": 0.10, "down": 0.20}

    with pytest.raises(ValueError, match="instrument_bands.*missing=.*ESZ6.*extra=.*MSFT"):
        load_bundle_payload(payload)


def test_load_installed_bundle_reads_package_manifest(tmp_path) -> None:
    package_dir = tmp_path / "aegis_exec_test_bundle"
    package_dir.mkdir()
    contract = _contract()
    (package_dir / "__init__.py").write_text("")
    (package_dir / "bundle_manifest.json").write_text(
        json.dumps(
            dump_bundle_payload(
                contract=contract,
                manifest=_manifest(contract),
                plan=_plan(contract.instrument_ids),
            )
        )
    )
    sys.path.insert(0, str(tmp_path))
    try:
        bundle = load_installed_bundle("aegis_exec_test_bundle")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("aegis_exec_test_bundle", None)

    assert bundle.contract == contract

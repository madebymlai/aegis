import json
import sys

import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    LockedExecutionPlan,
)
from aegis_runtime.bundle_loader import (
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

    assert payload["contract"]["instrument_ids"] == ["AAPL.NASDAQ", "ESZ6.XCME"]
    assert payload["plan"]["instrument_bands"] == {
        "AAPL.NASDAQ": {"up": 0.10, "down": 0.20},
        "ESZ6.XCME": {"up": 0.10, "down": 0.20},
    }
    assert bundle.contract == contract
    assert bundle.manifest == _manifest(contract)
    assert bundle.instrument_bands == plan.instrument_bands
    assert bundle.gross_cap == plan.gross_cap
    assert bundle.net_cap == plan.net_cap


def test_bundle_payload_round_trips_continuous_future_roots() -> None:
    """The continuous-root declaration must survive the wheel payload, or the additive-
    invariance guard (which keys off ``contract.futures``) is dead on a loaded bundle."""
    contract = DataContract(
        instrument_ids=(_id("ES.XCME"),),
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        lookback_bars=20,
        futures=("ES",),
    )

    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    assert payload["contract"]["futures"] == ["ES"]
    assert bundle.contract.futures == ("ES",)


def test_bundle_payload_without_futures_loads_as_no_roots() -> None:
    """A pre-r8b.9 wheel carries no ``futures`` key; it loads as no continuous roots
    (forward-safe default), so old bundles keep loading."""
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract, manifest=_manifest(contract), plan=_plan(contract.instrument_ids)
    )
    payload["contract"].pop("futures", None)

    bundle = load_bundle_payload(payload)

    assert bundle.contract.futures == ()


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

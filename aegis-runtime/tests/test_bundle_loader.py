import json
import sys
from collections.abc import Callable
from typing import Any

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.domain.drift_band import DriftBand
from aegis_runtime.domain.exposure_validation import InvalidExposureLimits
from aegis_runtime.execution.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DataContractError,
    ExecutionBundle,
    InvalidMissingIndexPolicy,
    LockedExecutionPlan,
    MissingIndexPolicy,
)
from aegis_runtime.execution.bundle_loader import (
    BundlePayloadFieldError,
    BundlePayloadSchemaError,
    load_bundle_payload,
    load_installed_bundle,
)

Payload = dict[str, Any]


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _contract() -> DataContract:
    return DataContract(
        instrument_ids=(_id("AAPL.NASDAQ"), _id("MSFT.NASDAQ")),
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


def _plan(instrument_ids: tuple[InstrumentId, ...]) -> LockedExecutionPlan:
    return LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategies",
            component_id="tests.strategy",
            module="bundle.strategy",
            input_names=("Close",),
            output_names=("target_weights",),
            params={"window": 5, "nested": {"thresholds": [0.1, 0.2]}},
        ),
        indicators=(),
        instrument_bands={
            instrument_id: DriftBand(up=0.10, down=0.20)
            for instrument_id in instrument_ids
        },
        direction="longonly",
    )


def _bundle(contract: DataContract | None = None) -> ExecutionBundle:
    contract = _contract() if contract is None else contract
    return ExecutionBundle(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(contract.instrument_ids),
    )


def _payload(bundle: ExecutionBundle | None = None) -> Payload:
    return (bundle or _bundle()).json_primitives()


@pytest.mark.parametrize(
    ("mode", "wire_value"),
    [
        (ContinuousFutureAdjustmentType.BACKWARD_RATIO, "backward_ratio"),
        (ContinuousFutureAdjustmentType.BACKWARD_SPREAD, "backward_spread"),
    ],
)
def test_v6_round_trips_native_continuous_future_facts(
    mode: ContinuousFutureAdjustmentType,
    wire_value: str,
) -> None:
    contract = DataContract(
        instrument_ids=(_id("ES.XCME"),),
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        futures=("ES",),
        adjustment_mode=mode,
    )
    bundle = _bundle(contract)

    raw = bundle.json()
    loaded = load_bundle_payload(raw)

    assert json.loads(raw)["contract"]["adjustment_mode"] == wire_value
    assert loaded.contract.futures == ("ES",)
    assert loaded.contract.adjustment_mode is mode


def test_v6_round_trips_exchange_legs_and_recorded_mark_modes() -> None:
    contract = DataContract(
        instrument_ids=(_id("UEQC.XETR"), _id("AAPL.NASDAQ")),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        exchange=(_id("EUR/USD.IDEALPRO"),),
        mark_modes={
            _id("UEQC.XETR"): "QUOTE",
            _id("AAPL.NASDAQ"): "LAST",
            _id("EUR/USD.IDEALPRO"): "MID",
        },
    )

    loaded = load_bundle_payload(_bundle(contract).json())

    assert loaded.contract.exchange == (_id("EUR/USD.IDEALPRO"),)
    assert loaded.contract.mark_modes == {
        _id("UEQC.XETR"): "QUOTE",
        _id("AAPL.NASDAQ"): "LAST",
        _id("EUR/USD.IDEALPRO"): "MID",
    }


def test_loader_rejects_v5_before_trusting_its_fields() -> None:
    payload = _payload()
    payload["schema_version"] = "execution_bundle.v5"

    with pytest.raises(BundlePayloadSchemaError, match="execution_bundle.v6"):
        load_bundle_payload(json.dumps(payload))


def test_loader_rejects_an_absent_schema_version() -> None:
    payload = _payload()
    del payload["schema_version"]

    with pytest.raises(BundlePayloadSchemaError, match="schema_version"):
        load_bundle_payload(json.dumps(payload))


def test_loader_reports_malformed_json_as_a_field_error() -> None:
    with pytest.raises(BundlePayloadFieldError):
        load_bundle_payload(b'{"schema_version":')


def _add_unknown_root(payload: Payload) -> None:
    payload["unknown"] = True


def _add_unknown_contract(payload: Payload) -> None:
    payload["contract"]["unknown"] = True


def _add_unknown_manifest(payload: Payload) -> None:
    payload["manifest"]["unknown"] = True


def _add_unknown_plan(payload: Payload) -> None:
    payload["plan"]["unknown"] = True


def _add_unknown_component(payload: Payload) -> None:
    payload["plan"]["strategy"]["unknown"] = True


def _add_unknown_drift_band(payload: Payload) -> None:
    payload["plan"]["instrument_bands"]["AAPL.NASDAQ"]["unknown"] = True


@pytest.mark.parametrize(
    ("add_unknown", "expected_path"),
    [
        pytest.param(_add_unknown_root, r"unknown field", id="root"),
        pytest.param(
            _add_unknown_contract,
            r"unknown field.*\$\.contract",
            id="contract",
        ),
        pytest.param(
            _add_unknown_manifest,
            r"unknown field.*\$\.manifest",
            id="manifest",
        ),
        pytest.param(_add_unknown_plan, r"unknown field.*\$\.plan", id="plan"),
        pytest.param(
            _add_unknown_component,
            r"unknown field.*\$\.plan\.strategy",
            id="component",
        ),
        pytest.param(
            _add_unknown_drift_band,
            r"unknown field.*\$\.plan\.instrument_bands",
            id="drift-band",
        ),
    ],
)
def test_loader_rejects_unknown_fields_at_every_struct_layer(
    add_unknown: Callable[[Payload], None],
    expected_path: str,
) -> None:
    payload = _payload()
    add_unknown(payload)

    with pytest.raises(BundlePayloadFieldError, match=expected_path):
        load_bundle_payload(json.dumps(payload))


def test_loader_reports_the_path_of_a_missing_required_field() -> None:
    payload = _payload()
    del payload["contract"]["missing_index"]

    with pytest.raises(
        BundlePayloadFieldError,
        match=r"missing required field `missing_index`.*\$\.contract",
    ):
        load_bundle_payload(json.dumps(payload))


def test_loader_reports_the_path_of_an_invalid_native_identifier() -> None:
    payload = _payload()
    payload["manifest"]["instrument_ids"][1] = ""

    with pytest.raises(
        BundlePayloadFieldError,
        match=r"\$\.manifest\.instrument_ids\[1\]",
    ):
        load_bundle_payload(json.dumps(payload))


def test_loader_preserves_a_named_data_contract_error() -> None:
    contract = DataContract(
        instrument_ids=(_id("ES.XCME"),),
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        futures=("ES",),
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )
    payload = _payload(_bundle(contract))
    del payload["contract"]["adjustment_mode"]

    with pytest.raises(DataContractError, match="no adjustment_mode"):
        load_bundle_payload(json.dumps(payload))


def test_loader_preserves_a_named_exposure_validation_error() -> None:
    payload = _payload()
    payload["plan"]["direction"] = "sideways"

    with pytest.raises(InvalidExposureLimits, match="direction must be one of"):
        load_bundle_payload(json.dumps(payload))


def test_loader_rejects_a_forward_adjustment_as_a_domain_error() -> None:
    contract = DataContract(
        instrument_ids=(_id("ES.XCME"),),
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        futures=("ES",),
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )
    payload = _payload(_bundle(contract))
    payload["contract"]["adjustment_mode"] = "forward_ratio"

    with pytest.raises(DataContractError, match="only backward modes"):
        load_bundle_payload(json.dumps(payload))


def test_loader_rejects_contract_and_plan_instrument_mismatch() -> None:
    payload = _payload()
    del payload["plan"]["instrument_bands"]["MSFT.NASDAQ"]
    payload["plan"]["instrument_bands"]["NVDA.NASDAQ"] = {"up": 0.1, "down": 0.2}

    with pytest.raises(
        BundlePayloadFieldError,
        match=r"instrument_bands.*missing=.*MSFT.*extra=.*NVDA",
    ):
        load_bundle_payload(json.dumps(payload))


def test_direct_contract_construction_requires_a_named_missing_index_policy() -> None:
    with pytest.raises(InvalidMissingIndexPolicy, match="must be one of"):
        DataContract(
            instrument_ids=(_id("AAPL.NASDAQ"),),
            required_arrays=("Close",),
            base_currency="USD",
            timeframe="1D",
            missing_index="drop",  # type: ignore[arg-type]
        )


def test_data_contract_rejects_exchange_overlapping_tradeables() -> None:
    with pytest.raises(ValueError, match="exchange"):
        DataContract(
            instrument_ids=(_id("AAPL.NASDAQ"),),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            exchange=(_id("AAPL.NASDAQ"),),
        )


def test_data_contract_rejects_a_mark_mode_outside_the_closed_set() -> None:
    with pytest.raises(DataContractError, match="closed set"):
        DataContract(
            instrument_ids=(_id("AAPL.NASDAQ"),),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            mark_modes={_id("AAPL.NASDAQ"): "TOUCH"},
        )


def test_load_installed_bundle_reads_native_json_bytes(tmp_path) -> None:
    package_dir = tmp_path / "aegis_exec_test_bundle"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    (package_dir / "bundle_manifest.json").write_bytes(_bundle().json())
    sys.path.insert(0, str(tmp_path))

    try:
        loaded = load_installed_bundle("aegis_exec_test_bundle")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("aegis_exec_test_bundle", None)

    assert loaded == _bundle()

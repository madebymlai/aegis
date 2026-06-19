import json
import sys

import pytest

from aegis_runtime import FuturesRef, ListedRef
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


def _contract() -> DataContract:
    return DataContract(
        refs=(
            ListedRef("BBG000000001"),
            FuturesRef(
                root="ES",
                dataset="cme",
                roll_rule="calendar",
                adjustment="continuous",
            ),
        ),
        required_arrays=("Close", "Open"),
        base_currency="EUR",
        required_fx_currencies=("USD",),
        timeframe="1D",
        lookback_bars=20,
    )


def _manifest(contract: DataContract) -> BundleManifest:
    return BundleManifest(
        run_id="run-1",
        role="best",
        candidate_key="0123456789abcdef",
        component_source_hashes={"strategies/test": "abc123"},
        refs=contract.refs,
    )


def _plan() -> LockedExecutionPlan:
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
        gross_cap=1.0,
        net_cap=None,
        direction="longonly",
        symbols=("SPY", "ES"),
        currency_by_symbol={"SPY": "USD", "ES": "USD"},
    )


def test_bundle_payload_round_trips_kind_tagged_refs() -> None:
    contract = _contract()
    plan = _plan()

    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=plan,
    )
    bundle = load_bundle_payload(json.loads(json.dumps(payload)))

    assert payload["contract"]["refs"] == [
        {"kind": "listed", "figi": "BBG000000001"},
        {
            "kind": "futures",
            "root": "ES",
            "dataset": "cme",
            "roll_rule": "calendar",
            "adjustment": "continuous",
        },
    ]
    assert bundle.contract == contract
    assert bundle.manifest == _manifest(contract)
    assert bundle.gross_cap == plan.gross_cap
    assert bundle.net_cap == plan.net_cap
    assert bundle.symbols == plan.symbols
    assert bundle.currency_by_symbol == plan.currency_by_symbol


def test_bundle_payload_rejects_ref_without_kind() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(),
    )
    del payload["contract"]["refs"][0]["kind"]

    with pytest.raises(ValueError, match="missing kind"):
        load_bundle_payload(payload)


def test_bundle_payload_rejects_unknown_ref_kind() -> None:
    contract = _contract()
    payload = dump_bundle_payload(
        contract=contract,
        manifest=_manifest(contract),
        plan=_plan(),
    )
    payload["manifest"]["refs"][1]["kind"] = "option"

    with pytest.raises(ValueError, match="unknown InstrumentRef kind"):
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
                plan=_plan(),
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

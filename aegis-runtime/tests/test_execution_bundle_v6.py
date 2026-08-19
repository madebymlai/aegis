import json

from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.domain.drift_band import DriftBand
from aegis_runtime.execution.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MissingIndexPolicy,
)
from aegis_runtime.execution.bundle_loader import load_bundle_payload


def test_execution_bundle_is_the_native_v6_artifact_root() -> None:
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    bundle = ExecutionBundle(
        contract=DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="USD",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
        ),
        manifest=BundleManifest(
            run_id="run-1",
            role="best",
            candidate_key="0123456789abcdef",
            component_source_hashes={"strategies/test": "abc123"},
            instrument_ids=(instrument_id,),
        ),
        plan=LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategies",
                component_id="test",
                module="bundle.strategy",
                input_names=("Close",),
                output_names=("target_weights",),
                params={"window": 5},
            ),
            indicators=(),
            instrument_bands={instrument_id: DriftBand(up=0.1, down=0.2)},
            direction="longonly",
        ),
    )

    raw = bundle.json()
    loaded = load_bundle_payload(raw)

    assert json.loads(raw) == {
        "contract": {
            "instrument_ids": ["AAPL.NASDAQ"],
            "required_arrays": ["Close"],
            "base_currency": "USD",
            "timeframe": "1D",
            "missing_index": "drop",
        },
        "manifest": {
            "run_id": "run-1",
            "role": "best",
            "candidate_key": "0123456789abcdef",
            "component_source_hashes": {"strategies/test": "abc123"},
            "instrument_ids": ["AAPL.NASDAQ"],
        },
        "plan": {
            "strategy": {
                "family": "strategies",
                "component_id": "test",
                "module": "bundle.strategy",
                "input_names": ["Close"],
                "output_names": ["target_weights"],
                "params": {"window": 5},
            },
            "indicators": [],
            "instrument_bands": {"AAPL.NASDAQ": {"up": 0.1, "down": 0.2}},
            "direction": "longonly",
        },
        "schema_version": "execution_bundle.v6",
    }
    assert loaded == bundle
    assert loaded.contract.instrument_ids == (instrument_id,)

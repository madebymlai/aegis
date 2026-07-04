from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
)
from aegis_runtime.drift_band import DriftBand

BUNDLE_PAYLOAD_SCHEMA_VERSION = "execution_bundle.v3"


class BundlePayloadError(ValueError):
    """A serialized Execution Bundle payload is malformed."""


class BundlePayloadSchemaError(BundlePayloadError):
    """The serialized bundle payload has an unsupported schema."""


class BundlePayloadFieldError(BundlePayloadError):
    """The serialized bundle payload is missing a required field."""


def dump_bundle_payload(
    *,
    contract: DataContract,
    manifest: BundleManifest,
    plan: LockedExecutionPlan,
) -> dict[str, Any]:
    return {
        "schema_version": BUNDLE_PAYLOAD_SCHEMA_VERSION,
        "contract": {
            "instrument_ids": [_dump_instrument_id(item) for item in contract.instrument_ids],
            "required_arrays": list(contract.required_arrays),
            "base_currency": contract.base_currency,
            "timeframe": contract.timeframe,
            "missing_index": contract.missing_index.value,
            "lookback_bars": contract.lookback_bars,
            "futures": list(contract.futures),
            "exchange": [_dump_instrument_id(item) for item in contract.exchange],
        },
        "manifest": {
            "run_id": manifest.run_id,
            "role": manifest.role,
            "candidate_key": manifest.candidate_key,
            "component_source_hashes": dict(manifest.component_source_hashes),
            "instrument_ids": [_dump_instrument_id(item) for item in manifest.instrument_ids],
        },
        "plan": {
            "strategy": _dump_component_spec(plan.strategy),
            "indicators": [_dump_component_spec(spec) for spec in plan.indicators],
            "instrument_bands": _dump_instrument_bands(plan.instrument_bands),
            "gross_cap": plan.gross_cap,
            "net_cap": plan.net_cap,
            "direction": plan.direction,
        },
    }


def load_bundle_payload(payload: Mapping[str, Any]) -> ExecutionBundle:
    schema_version = _required_schema_version(payload)
    if schema_version != BUNDLE_PAYLOAD_SCHEMA_VERSION:
        raise BundlePayloadSchemaError(
            "bundle payload schema_version must be "
            f"{BUNDLE_PAYLOAD_SCHEMA_VERSION!r}; got {schema_version!r}"
        )
    contract_payload = _required_mapping(payload, "contract", "bundle payload")
    manifest_payload = _required_mapping(payload, "manifest", "bundle payload")
    plan_payload = _required_mapping(payload, "plan", "bundle payload")
    contract = DataContract(
        instrument_ids=tuple(
            _load_instrument_id(item)
            for item in _required_sequence(contract_payload, "instrument_ids", "DataContract")
        ),
        required_arrays=tuple(
            _required_sequence(contract_payload, "required_arrays", "DataContract")
        ),
        base_currency=_required_value(contract_payload, "base_currency", "DataContract"),
        timeframe=_required_value(contract_payload, "timeframe", "DataContract"),
        missing_index=_required_value(contract_payload, "missing_index", "DataContract"),
        lookback_bars=_required_value(contract_payload, "lookback_bars", "DataContract"),
        futures=tuple(_required_sequence(contract_payload, "futures", "DataContract")),
        exchange=tuple(
            _load_instrument_id(item)
            for item in _required_sequence(contract_payload, "exchange", "DataContract")
        ),
    )
    manifest = BundleManifest(
        run_id=_required_value(manifest_payload, "run_id", "BundleManifest"),
        role=_required_value(manifest_payload, "role", "BundleManifest"),
        candidate_key=_required_value(manifest_payload, "candidate_key", "BundleManifest"),
        component_source_hashes=_required_mapping(
            manifest_payload, "component_source_hashes", "BundleManifest"
        ),
        instrument_ids=tuple(
            _load_instrument_id(item)
            for item in _required_sequence(manifest_payload, "instrument_ids", "BundleManifest")
        ),
    )
    plan = LockedExecutionPlan(
        strategy=_load_component_spec(_required_mapping(plan_payload, "strategy", "plan")),
        indicators=tuple(
            _load_component_spec(_ensure_mapping(item, "LockedExecutionPlan.indicators item"))
            for item in _required_sequence(plan_payload, "indicators", "LockedExecutionPlan")
        ),
        instrument_bands=_load_instrument_bands(
            _required_mapping(plan_payload, "instrument_bands", "LockedExecutionPlan")
        ),
        gross_cap=_required_value(plan_payload, "gross_cap", "LockedExecutionPlan"),
        net_cap=plan_payload.get("net_cap"),
        direction=_required_value(plan_payload, "direction", "LockedExecutionPlan"),
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def load_installed_bundle(package: str) -> ExecutionBundle:
    manifest = resources.files(package).joinpath("bundle_manifest.json")
    return load_bundle_payload(json.loads(manifest.read_text(encoding="utf-8")))


def _dump_component_spec(spec: ComponentSpec) -> dict[str, Any]:
    return {
        "family": spec.family,
        "component_id": spec.component_id,
        "module": spec.module,
        "input_names": list(spec.input_names),
        "output_names": list(spec.output_names),
        "params": dict(spec.params),
    }


def _load_component_spec(payload: Mapping[str, Any]) -> ComponentSpec:
    return ComponentSpec(
        family=_required_value(payload, "family", "ComponentSpec"),
        component_id=_required_value(payload, "component_id", "ComponentSpec"),
        module=_required_value(payload, "module", "ComponentSpec"),
        input_names=tuple(_required_sequence(payload, "input_names", "ComponentSpec")),
        output_names=tuple(_required_sequence(payload, "output_names", "ComponentSpec")),
        params=_required_mapping(payload, "params", "ComponentSpec"),
    )


def _dump_instrument_bands(bands: Mapping[InstrumentId, DriftBand]) -> dict[str, dict[str, float]]:
    return {
        instrument_id.value: _dump_drift_band(bands[instrument_id])
        for instrument_id in sorted(bands, key=lambda item: item.value)
    }


def _load_instrument_bands(payload: Mapping[str, Any]) -> dict[InstrumentId, DriftBand]:
    return {
        _load_instrument_id(instrument_id): _load_drift_band(
            _ensure_mapping(value, "LockedExecutionPlan.instrument_bands item")
        )
        for instrument_id, value in payload.items()
    }


def _dump_drift_band(band: DriftBand) -> dict[str, float]:
    return {
        "up": band.up,
        "down": band.down,
        "destination_fraction": band.destination_fraction,
    }


def _load_drift_band(payload: Mapping[str, Any]) -> DriftBand:
    return DriftBand(
        up=_required_value(payload, "up", "DriftBand"),
        down=_required_value(payload, "down", "DriftBand"),
        # Optional: older bundles carry no destination; 1.0 is their exact
        # trade-to-target behaviour (forward-safe default).
        destination_fraction=payload.get("destination_fraction", 1.0),
    )


def _dump_instrument_id(instrument_id: InstrumentId) -> str:
    return instrument_id.value


def _load_instrument_id(value: Any) -> InstrumentId:
    if not isinstance(value, str) or not value:
        raise ValueError(f"InstrumentId must be a non-empty string; got {value!r}")
    return InstrumentId.from_str(value)


def _required_mapping(
    payload: Mapping[str, Any], field: str, owner: str
) -> Mapping[str, Any]:
    return _ensure_mapping(_required_value(payload, field, owner), f"{owner}.{field}")


def _required_sequence(payload: Mapping[str, Any], field: str, owner: str) -> list[Any]:
    value = _required_value(payload, field, owner)
    if not isinstance(value, list):
        raise ValueError(f"{owner}.{field} must be a list; got {value!r}")
    return value


def _required_value(payload: Mapping[str, Any], field: str, owner: str) -> Any:
    try:
        return payload[field]
    except KeyError:
        raise BundlePayloadFieldError(
            f"{owner} is missing required field {field!r}"
        ) from None


def _required_schema_version(payload: Mapping[str, Any]) -> Any:
    try:
        return payload["schema_version"]
    except KeyError:
        raise BundlePayloadSchemaError(
            "bundle payload is missing required field 'schema_version'"
        ) from None


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping; got {value!r}")
    return value

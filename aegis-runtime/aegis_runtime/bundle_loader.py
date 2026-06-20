from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
)
from aegis_runtime.instruments import FuturesRef, InstrumentRef, ListedRef


def dump_bundle_payload(
    *,
    contract: DataContract,
    manifest: BundleManifest,
    plan: LockedExecutionPlan,
) -> dict[str, Any]:
    return {
        "contract": {
            "refs": [_dump_instrument_ref(ref) for ref in contract.refs],
            "required_arrays": list(contract.required_arrays),
            "base_currency": contract.base_currency,
            "required_fx_currencies": list(contract.required_fx_currencies),
            "timeframe": contract.timeframe,
            "lookback_bars": contract.lookback_bars,
        },
        "manifest": {
            "run_id": manifest.run_id,
            "role": manifest.role,
            "candidate_key": manifest.candidate_key,
            "component_source_hashes": dict(manifest.component_source_hashes),
            "refs": [_dump_instrument_ref(ref) for ref in manifest.refs],
        },
        "plan": {
            "strategy": _dump_component_spec(plan.strategy),
            "indicators": [_dump_component_spec(spec) for spec in plan.indicators],
            "gross_cap": plan.gross_cap,
            "net_cap": plan.net_cap,
            "direction": plan.direction,
            "symbols": list(plan.symbols),
            "currency_by_symbol": dict(plan.currency_by_symbol),
        },
    }


def load_bundle_payload(payload: Mapping[str, Any]) -> ExecutionBundle:
    contract_payload = _required_mapping(payload, "contract", "bundle payload")
    manifest_payload = _required_mapping(payload, "manifest", "bundle payload")
    plan_payload = _required_mapping(payload, "plan", "bundle payload")
    contract = DataContract(
        refs=tuple(
            _load_instrument_ref(item)
            for item in _required_sequence(contract_payload, "refs", "DataContract")
        ),
        required_arrays=tuple(
            _required_sequence(contract_payload, "required_arrays", "DataContract")
        ),
        base_currency=_required_value(contract_payload, "base_currency", "DataContract"),
        required_fx_currencies=tuple(
            _required_sequence(contract_payload, "required_fx_currencies", "DataContract")
        ),
        timeframe=_required_value(contract_payload, "timeframe", "DataContract"),
        lookback_bars=_required_value(contract_payload, "lookback_bars", "DataContract"),
    )
    manifest = BundleManifest(
        run_id=_required_value(manifest_payload, "run_id", "BundleManifest"),
        role=_required_value(manifest_payload, "role", "BundleManifest"),
        candidate_key=_required_value(manifest_payload, "candidate_key", "BundleManifest"),
        component_source_hashes=_required_mapping(
            manifest_payload, "component_source_hashes", "BundleManifest"
        ),
        refs=tuple(
            _load_instrument_ref(item)
            for item in _required_sequence(manifest_payload, "refs", "BundleManifest")
        ),
    )
    plan = LockedExecutionPlan(
        strategy=_load_component_spec(_required_mapping(plan_payload, "strategy", "plan")),
        indicators=tuple(
            _load_component_spec(_ensure_mapping(item, "LockedExecutionPlan.indicators item"))
            for item in _required_sequence(plan_payload, "indicators", "LockedExecutionPlan")
        ),
        gross_cap=_required_value(plan_payload, "gross_cap", "LockedExecutionPlan"),
        net_cap=plan_payload.get("net_cap"),
        direction=_required_value(plan_payload, "direction", "LockedExecutionPlan"),
        symbols=tuple(_required_sequence(plan_payload, "symbols", "LockedExecutionPlan")),
        currency_by_symbol=_required_mapping(
            plan_payload, "currency_by_symbol", "LockedExecutionPlan"
        ),
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


def _dump_instrument_ref(ref: InstrumentRef) -> dict[str, str]:
    if isinstance(ref, ListedRef):
        return {"kind": "listed", "figi": ref.figi}
    if isinstance(ref, FuturesRef):
        return {
            "kind": "futures",
            "root": ref.root,
            "dataset": ref.dataset,
            "roll_rule": ref.roll_rule,
            "adjustment": ref.adjustment,
        }
    raise ValueError(f"InstrumentRef must be ListedRef or FuturesRef; got {ref!r}")


def _load_instrument_ref(value: Any) -> InstrumentRef:
    payload = _ensure_mapping(value, "InstrumentRef")
    kind = payload.get("kind")
    if kind is None:
        raise ValueError("InstrumentRef payload is missing kind")
    if kind == "listed":
        return ListedRef(figi=_required_value(payload, "figi", "ListedRef"))
    if kind == "futures":
        return FuturesRef(
            root=_required_value(payload, "root", "FuturesRef"),
            dataset=_required_value(payload, "dataset", "FuturesRef"),
            roll_rule=_required_value(payload, "roll_rule", "FuturesRef"),
            adjustment=_required_value(payload, "adjustment", "FuturesRef"),
        )
    raise ValueError(f"unknown InstrumentRef kind {kind!r}")


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
        raise ValueError(f"{owner} is missing required field {field!r}") from None


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping; got {value!r}")
    return value

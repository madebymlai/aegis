from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

from pydantic import ConfigDict, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from pydantic.dataclasses import dataclass as pydantic_dataclass

from aegis_runtime.bundle import (
    DataContractError,
    BundleManifest,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
)

# v5 (aegis-rd-ui1m): the plan no longer carries gross_cap/net_cap — unit gross
# is the fixed sleeve contract (bundle.SLEEVE_GROSS_LIMIT), not a locked number.
BUNDLE_PAYLOAD_SCHEMA_VERSION = "execution_bundle.v5"


class BundlePayloadError(ValueError):
    """A serialized Execution Bundle payload is malformed."""


class BundlePayloadSchemaError(BundlePayloadError):
    """The serialized bundle payload has an unsupported schema."""


class BundlePayloadFieldError(BundlePayloadError):
    """The serialized bundle payload is missing a required field."""


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class _BundlePayload:
    """The wire envelope: the three bundle parts under a schema version.

    Its fields carry their own wire form (see `bundle.WireInstrumentId` and
    friends), so this one declaration serves both directions — there is no
    hand-mirrored dumper to keep in step with the loader.
    """

    schema_version: str
    contract: DataContract
    manifest: BundleManifest
    plan: LockedExecutionPlan


_PAYLOAD_ADAPTER = TypeAdapter(_BundlePayload)

# Derived from the types themselves, so a new bundle field is mandatory on the
# wire the moment it is declared — there is no second list to update. Computed
# fields (init=False, e.g. the plan's exposure limits) never travel.
_PAYLOAD_SECTION_FIELDS: dict[str, frozenset[str]] = {
    section: frozenset(f.name for f in dataclasses.fields(part_type) if f.init)
    for section, part_type in (
        ("contract", DataContract),
        ("manifest", BundleManifest),
        ("plan", LockedExecutionPlan),
    )
}


def dump_bundle_payload(
    *,
    contract: DataContract,
    manifest: BundleManifest,
    plan: LockedExecutionPlan,
) -> dict[str, Any]:
    payload = _BundlePayload(
        schema_version=BUNDLE_PAYLOAD_SCHEMA_VERSION,
        contract=contract,
        manifest=manifest,
        plan=plan,
    )
    dumped = _PAYLOAD_ADAPTER.dump_python(payload, mode="json")
    # `adjustment_mode` is absent, not null, when a bundle declares no futures.
    if dumped["contract"].get("adjustment_mode") is None:
        dumped["contract"].pop("adjustment_mode", None)
    return dumped


def load_bundle_payload(payload: Mapping[str, Any]) -> ExecutionBundle:
    # Version negotiation precedes field validation: an unreadable schema is a
    # different failure from a malformed field, and keeps its own error type.
    schema_version = _required_schema_version(payload)
    if schema_version != BUNDLE_PAYLOAD_SCHEMA_VERSION:
        raise BundlePayloadSchemaError(
            "bundle payload schema_version must be "
            f"{BUNDLE_PAYLOAD_SCHEMA_VERSION!r}; got {schema_version!r}"
        )
    _require_wire_keys(payload)
    try:
        loaded = _PAYLOAD_ADAPTER.validate_python(payload)
    except PydanticValidationError as error:
        # A structurally sound payload can still describe an inconsistent
        # contract (futures without an adjustment mode). That is the domain's
        # verdict, not the wire's, so its own error crosses this boundary
        # untranslated — only malformed-payload failures become field errors.
        _reraise_domain_error(error)
        raise BundlePayloadFieldError(_format_payload_errors(error)) from error
    return ExecutionBundle(
        contract=loaded.contract,
        manifest=loaded.manifest,
        plan=loaded.plan,
    )


def load_installed_bundle(package: str) -> ExecutionBundle:
    manifest = resources.files(package).joinpath("bundle_manifest.json")
    return load_bundle_payload(json.loads(manifest.read_text(encoding="utf-8")))


# A v5 payload states every field it carries — a defaulted field on the type is
# still mandatory on the wire, so an old wheel missing one fails loudly instead
# of silently acquiring today's default. This is a presence-in-raw rule, not a
# property of the constructed type (ADR-0012), so it stays here rather than
# becoming a second, wire-only view of the bundle types. The two exceptions are
# recorded absences: a bundle with no futures has no adjustment_mode, and a
# pre-tggo.3 wheel recorded no mark_modes.
_OPTIONAL_WIRE_KEYS = {"contract": frozenset({"adjustment_mode", "mark_modes"})}


def _require_wire_keys(payload: Mapping[str, Any]) -> None:
    for section, declared in _PAYLOAD_SECTION_FIELDS.items():
        raw = payload.get(section)
        if not isinstance(raw, Mapping):
            continue  # shape is pydantic's to reject
        optional = _OPTIONAL_WIRE_KEYS.get(section, frozenset())
        missing = sorted(declared - optional - set(raw))
        if missing:
            raise BundlePayloadFieldError(
                f"{section} is missing required field{'s' if len(missing) > 1 else ''} "
                f"{', '.join(repr(name) for name in missing)}"
            )
        # Absence is how the wire says "not recorded"; an explicit null is not a
        # synonym for it, and must not reach the type's own optional default.
        nulled = sorted(name for name in optional if name in raw and raw[name] is None)
        if nulled:
            raise BundlePayloadFieldError(
                f"{section} field{'s' if len(nulled) > 1 else ''} "
                f"{', '.join(repr(name) for name in nulled)} must be omitted when unset, not null"
            )


def _reraise_domain_error(error: PydanticValidationError) -> None:
    """Re-raise the domain's own verdict when it caused the validation failure."""
    for entry in error.errors():
        cause = entry.get("ctx", {}).get("error")
        if isinstance(cause, DataContractError):
            raise cause


def _format_payload_errors(error: PydanticValidationError) -> str:
    """Accumulate every payload error into one message, dotted-path first."""
    messages: list[str] = []
    for entry in error.errors(include_url=False):
        loc = ".".join(str(part) for part in entry.get("loc", ()))
        messages.append(f"{loc}: {entry['msg']}" if loc else entry["msg"])
    return "; ".join(messages)


def _required_schema_version(payload: Mapping[str, Any]) -> Any:
    try:
        return payload["schema_version"]
    except KeyError:
        raise BundlePayloadSchemaError(
            "bundle payload is missing required field 'schema_version'"
        ) from None

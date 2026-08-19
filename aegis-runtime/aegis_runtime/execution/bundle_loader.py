from __future__ import annotations

from importlib import resources
from typing import Any

import msgspec

from aegis_runtime.domain.exposure_validation import ExposureValidationError
from aegis_runtime.execution.bundle import (
    BUNDLE_PAYLOAD_SCHEMA_VERSION,
    DataContractError,
    ExecutionBundle,
)


class BundlePayloadError(ValueError):
    """A serialized Execution Bundle payload is malformed."""


class BundlePayloadSchemaError(BundlePayloadError):
    """The serialized bundle payload has an unsupported schema."""


class BundlePayloadFieldError(BundlePayloadError):
    """The serialized bundle payload contains malformed fields."""


def load_bundle_payload(raw: bytes | str) -> ExecutionBundle:
    """Negotiate the Aegis artifact schema and parse its native root config."""
    schema_version = _required_schema_version(raw)
    if schema_version != BUNDLE_PAYLOAD_SCHEMA_VERSION:
        raise BundlePayloadSchemaError(
            "bundle payload schema_version must be "
            f"{BUNDLE_PAYLOAD_SCHEMA_VERSION!r}; got {schema_version!r}"
        )
    try:
        return ExecutionBundle.parse(raw)
    except msgspec.ValidationError as error:
        if isinstance(error.__cause__, (DataContractError, ExposureValidationError)):
            raise error.__cause__
        raise BundlePayloadFieldError(str(error)) from error
    except msgspec.DecodeError as error:
        raise BundlePayloadFieldError(str(error)) from error


def load_installed_bundle(package: str) -> ExecutionBundle:
    manifest = resources.files(package).joinpath("bundle_manifest.json")
    return load_bundle_payload(manifest.read_bytes())


def _required_schema_version(raw: bytes | str) -> Any:
    try:
        payload = msgspec.json.decode(raw)
    except msgspec.DecodeError as error:
        raise BundlePayloadFieldError(str(error)) from error
    if not isinstance(payload, dict):
        raise BundlePayloadFieldError("bundle payload must be a JSON object")
    try:
        return payload["schema_version"]
    except KeyError:
        raise BundlePayloadSchemaError(
            "bundle payload is missing required field 'schema_version'"
        ) from None

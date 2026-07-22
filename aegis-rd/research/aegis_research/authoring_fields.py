"""Shared Pydantic vocabulary for Aegis RD authoring contracts.

This neutral leaf is imported by both Run Config models and Component manifests.
It must not depend on either authoring surface.
"""

from __future__ import annotations

from typing import Annotated

import pandas as pd
from aegis_runtime import validate_bare_root
from pydantic import AfterValidator, Field

IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.-]+$"
RUN_NAME_PATTERN = (
    r"^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*|"
    r"\.[A-Za-z0-9_-][A-Za-z0-9_.-]*|\.\.[A-Za-z0-9_.-]+)$"
)


def _validate_timedelta_str(value: str) -> str:
    """Require a value that pandas can parse as a Timedelta."""
    try:
        pd.Timedelta(value)
    except ValueError:
        raise ValueError("must be a pandas Timedelta string (e.g. '1D')") from None
    return value


def has_data_array_token_shape(value: str) -> bool:
    """Return whether an authored Array name has the shared token shape."""
    return bool(value) and value.strip() == value and not any(char in "\t\n\r" for char in value)


PositiveCash = Annotated[float, Field(strict=True, gt=0)]
NonNegativeCash = Annotated[float, Field(strict=True, ge=0)]
NonNegativeRate = Annotated[float, Field(strict=True, ge=0)]
UnitInterval = Annotated[float, Field(strict=True, ge=0, le=1)]
ComponentIdStr = Annotated[str, Field(min_length=1, pattern=IDENTIFIER_PATTERN)]
RunName = Annotated[
    str,
    Field(pattern=RUN_NAME_PATTERN),
]
NonEmptyStr = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
TimedeltaStr = Annotated[str, AfterValidator(_validate_timedelta_str)]
# A bare continuous-future root symbol (e.g. "ES"); rejects venue-qualified ids.
# Shares one validator with live's DataContract.futures.
RootSymbol = Annotated[str, AfterValidator(validate_bare_root)]

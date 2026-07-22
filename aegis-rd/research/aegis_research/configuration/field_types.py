"""Domain-type vocabulary for pydantic v2 dataclass fields.

Each type is an ``Annotated[float, Field(...)]`` that carries the named constraint.
Strict ``float`` accepts ``int`` (coerces to float) and rejects ``bool`` / ``str``.
"""

from __future__ import annotations

import re
from typing import Annotated

import pandas as pd
from aegis_runtime import validate_bare_root
from pydantic import AfterValidator, Field

IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.-]+$"
IDENTIFIER_RE = re.compile(IDENTIFIER_PATTERN)


def _validate_timedelta_str(value: str) -> str:
    """Pydantic item-validator: the value must parse as a pandas Timedelta."""
    try:
        pd.Timedelta(value)
    except ValueError:
        raise ValueError("must be a pandas Timedelta string (e.g. '1D')") from None
    return value


PositiveCash = Annotated[float, Field(strict=True, gt=0)]
NonNegativeCash = Annotated[float, Field(strict=True, ge=0)]
NonNegativeRate = Annotated[float, Field(strict=True, ge=0)]
UnitInterval = Annotated[float, Field(strict=True, ge=0, le=1)]
ComponentIdStr = Annotated[str, Field(min_length=1, pattern=IDENTIFIER_PATTERN)]
NonEmptyStr = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
TimedeltaStr = Annotated[str, AfterValidator(_validate_timedelta_str)]  # annualization calendar
# A bare continuous-future root symbol (e.g. "ES"); rejects venue-qualified ids ("ES.XCME").
# Shares one validator with live's DataContract.futures so research and live agree byte-for-byte.
RootSymbol = Annotated[str, AfterValidator(validate_bare_root)]

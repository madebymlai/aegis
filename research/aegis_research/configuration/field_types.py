"""Domain-type vocabulary for pydantic v2 dataclass fields.

Each type is an ``Annotated[float, Field(...)]`` that carries the named constraint.
Strict ``float`` accepts ``int`` (coerces to float) and rejects ``bool`` / ``str``.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field

EXPERIMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
EXPERIMENT_NAME_PATTERN = r"^[A-Za-z0-9_.-]+$"

StrictFloat = Annotated[float, Field(strict=True)]
PositiveCash = Annotated[float, Field(strict=True, gt=0)]
NonNegativeRate = Annotated[float, Field(strict=True, ge=0)]
UnitInterval = Annotated[float, Field(strict=True, ge=0, le=1)]
ComponentIdStr = Annotated[str, Field(min_length=1, pattern=EXPERIMENT_NAME_PATTERN)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]

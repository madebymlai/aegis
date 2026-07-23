from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class InvalidRunIdError(ValueError):
    """A supplied Run ID is outside the supported identity grammar."""


@dataclass(frozen=True, order=True)
class RunId:
    """Validated identity for one attempted Run."""

    value: str

    def __post_init__(self) -> None:
        if not RUN_ID_PATTERN.fullmatch(self.value) or self.value in {".", ".."}:
            raise InvalidRunIdError(
                "run_id must contain only letters, numbers, dots, underscores, and hyphens"
            )

    @classmethod
    def create(cls, value: str | None, *, run_name: str) -> RunId:
        if value is not None:
            return cls(value)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return cls(f"{timestamp}_{run_name}")

    def __str__(self) -> str:
        return self.value


__all__ = ["InvalidRunIdError", "RunId"]

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, order=True)
class ListedRef:
    """InstrumentRef for a permanently listed instrument, identified by FIGI."""

    figi: str

    def __post_init__(self) -> None:
        if not isinstance(self.figi, str) or not self.figi:
            raise ValueError(f"ListedRef FIGI must be a non-empty string; got {self.figi!r}")

    @property
    def value(self) -> str:
        """Stable string payload used where a human-readable label is needed."""
        return self.figi


@dataclass(frozen=True, order=True)
class FuturesRef:
    """InstrumentRef for a continuous futures exposure."""

    root: str
    dataset: str
    roll_rule: str = "calendar"
    adjustment: str = "unadjusted"

    def __post_init__(self) -> None:
        for name, value in (
            ("root", self.root),
            ("dataset", self.dataset),
            ("roll_rule", self.roll_rule),
            ("adjustment", self.adjustment),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"FuturesRef {name} must be a non-empty string; got {value!r}")

    @property
    def value(self) -> str:
        """Stable string payload used where a human-readable label is needed."""
        return f"{self.dataset}:{self.root}:{self.roll_rule}:{self.adjustment}"


InstrumentRef: TypeAlias = ListedRef | FuturesRef

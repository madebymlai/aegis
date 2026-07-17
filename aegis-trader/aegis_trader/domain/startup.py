"""Pure startup halt vocabulary shared by trader modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StartupGate(str, Enum):
    """Startup gate responsible for a startup halt."""

    ACCOUNT_INTEGRITY = "account_integrity"
    CONTINUOUS_IDENTITY = "continuous_identity"


@dataclass(frozen=True)
class StartupResult:
    """Result of the startup checks that decide whether the book may trade."""

    trading_enabled: bool
    halt_gate: StartupGate | None = None
    halt_reason: str | None = None
    nav: float | None = None
    cash: float | None = None

    @property
    def should_halt(self) -> bool:
        """Whether the Strategy must idle instead of trading."""
        return not self.trading_enabled

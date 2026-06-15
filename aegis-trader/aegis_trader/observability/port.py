"""ObservabilityPort — abstraction over structured logging and alerting.

Pure domain component: defines the port protocol and the domain value types
(`RebalanceSummary`, `GateOutcome`) that the rebalancer and strategy use.  The
Nautilus-backed adapter lives in `observability/nautilus.py` and implements
this port using the Nautilus `MessageBus` + `LoggingConfig`.

ADR-0003: `domain/` imports no Nautilus types.  The port speaks only domain
identities and plain types, so core domain logic can emit structured logs
without coupling to the framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class GateOutcome(str, Enum):
    """Outcome of the cap/band gate during a rebalance."""

    PASS = "pass"
    HALT = "halt"  # integrity failure → global halt
    ERROR = "error"  # gate raised (remediation failed or unfixable)


@dataclass(frozen=True)
class RebalanceSummary:
    """Structured summary of one rebalance decision.

    Captures the key outcomes — targets, trades, gate status — for structured
    logging at each rebalance.  All monetary values in base currency (EUR) or
    weight fractions.
    """

    nav: float
    """Account NAV at the time of the rebalance (base currency)."""

    num_sleeves: int
    """Number of sleeves that produced targets this period."""

    num_targets: int
    """Number of distinct FIGIs with non-zero net targets."""

    num_orders: int
    """Number of OrderIntents emitted (before venue-open filter)."""

    num_quarantined: int
    """Number of held-but-untracked FIGIs quarantined this period."""

    quarantined_figis: tuple[str, ...]
    """FIGIs that were quarantined (held position, no sleeve contract)."""

    gate_outcome: GateOutcome
    """Whether the gate passed, halted, or raised an error."""

    total_notional: float
    """Sum of absolute EUR notionals for all OrderIntents."""


@runtime_checkable
class ObservabilityPort(Protocol):
    """Protocol for structured rebalance logging and alerting.

    Implementations wire this to a concrete observability backend
    (Nautilus MessageBus, CloudWatch, Prometheus, etc.) without
    the domain core ever depending on the backend.
    """

    def log_rebalance_decision(self, summary: RebalanceSummary) -> None:
        """Emit a structured log of one rebalance decision.

        Called by the strategy after each rebalance — includes targets,
        trades, gate outcome, and quarantine state.
        """
        ...

    def alert_quarantine(self, figis: tuple[str, ...]) -> None:
        """Alert that instruments are quarantined (held, no sleeve contract).

        Quarantined instruments are counted in the gate but never traded.
        Operators must investigate and manually wind down these positions.
        """
        ...

    def alert_halt(self, reason: str) -> None:
        """Alert that the book has been globally halted.

        Called when the account-integrity check fails at startup or when
        an unfixable gate breach occurs.  The book stops trading until the
        operator clears the halt.
        """
        ...

    def log_info(self, message: str) -> None:
        """Log an informational message."""
        ...

    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        ...

    def log_error(self, message: str) -> None:
        """Log an error message."""
        ...

"""Append-only, event-local observations for the cash-merger research shadow."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from .artifacts import canonical_bytes, write_once


class EventStatus(StrEnum):
    """An observed state of one identified merger agreement."""

    ANNOUNCED = "announced"
    AMENDED = "amended"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    REPLACED = "replaced"


@dataclass(frozen=True)
class EventObservation:
    """One immutable fact available at a known time for one agreement."""

    event_id: str
    target_cik: str
    ticker: str
    agreement_accession: str
    agreement_date: str
    observed_at: str
    status: EventStatus
    offer_price: float | None
    source_accession: str
    source_url: str
    evidence: str


@dataclass(frozen=True)
class LedgerWrite:
    """Observable result of replaying source observations into the ledger."""

    added: int
    existing: int


@dataclass(frozen=True)
class ShadowQualification:
    """The frozen evidence gate for attempting another alpha evaluation."""

    resolved_events: int
    adverse_resolutions: int
    minimum_resolved_events: int
    minimum_adverse_resolutions: int
    ready_for_alpha_evaluation: bool


class ShadowLedger:
    """Own immutable persistence and causal replay of merger observations."""

    def __init__(self, root: Path) -> None:
        self._observations = root / "observations"

    def record(self, observations: Iterable[EventObservation]) -> LedgerWrite:
        added = 0
        existing = 0
        for observation in observations:
            payload = _payload(observation)
            identity = hashlib.sha256(payload).hexdigest()
            destination = self._observations / f"{identity}.json"
            if destination.exists():
                existing += 1
                continue
            self._observations.mkdir(parents=True, exist_ok=True)
            write_once(destination, payload)
            added += 1
        return LedgerWrite(added=added, existing=existing)

    def events(self, *, as_of: datetime) -> tuple[EventObservation, ...]:
        cutoff = _aware(as_of)
        observations = (_load(path) for path in self._observations.glob("*.json"))
        available = (
            observation
            for observation in observations
            if _aware(datetime.fromisoformat(observation.observed_at)) <= cutoff
        )
        return tuple(
            sorted(
                available,
                key=lambda item: (
                    item.observed_at,
                    item.event_id,
                    item.source_accession,
                    _STATUS_ORDER[item.status],
                ),
            )
        )

    def states(self, *, as_of: datetime) -> tuple[EventObservation, ...]:
        """Return the latest causally available observation for every agreement."""

        latest: dict[str, EventObservation] = {}
        for observation in self.events(as_of=as_of):
            latest[observation.event_id] = observation
        return tuple(latest[event_id] for event_id in sorted(latest))

    def qualification(self, *, as_of: datetime) -> ShadowQualification:
        states = self.states(as_of=as_of)
        resolved = sum(
            state.status in {EventStatus.COMPLETED, EventStatus.TERMINATED, EventStatus.REPLACED}
            for state in states
        )
        adverse = sum(state.status is EventStatus.TERMINATED for state in states)
        return ShadowQualification(
            resolved_events=resolved,
            adverse_resolutions=adverse,
            minimum_resolved_events=100,
            minimum_adverse_resolutions=10,
            ready_for_alpha_evaluation=resolved >= 100 and adverse >= 10,
        )


def _payload(observation: EventObservation) -> bytes:
    return canonical_bytes(asdict(observation))


def _load(path: Path) -> EventObservation:
    payload = json.loads(path.read_text())
    payload["status"] = EventStatus(payload["status"])
    return EventObservation(**payload)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("shadow ledger timestamps must include a timezone")
    return value


_STATUS_ORDER = {
    EventStatus.ANNOUNCED: 0,
    EventStatus.AMENDED: 1,
    EventStatus.COMPLETED: 2,
    EventStatus.TERMINATED: 2,
    EventStatus.REPLACED: 2,
}

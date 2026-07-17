"""One end-to-end prospective cash-merger research shadow run."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from .artifacts import canonical_bytes, write_once
from .decision import (
    FrozenQ70Policy,
    ShadowDecision,
    ShadowPosition,
)
from .ledger import (
    EventObservation,
    EventStatus,
    ShadowLedger,
    ShadowQualification,
)
from .market import MarketMarkBatch, MarketUnavailable
from .sec_api import SourceRefresh


class ShadowEventSource(Protocol):
    def refresh(
        self,
        *,
        start: date,
        end: date,
        active_events: Iterable[EventObservation],
    ) -> SourceRefresh: ...


class ShadowMarkSource(Protocol):
    def load(
        self,
        events: Iterable[EventObservation],
        *,
        as_of: datetime,
    ) -> MarketMarkBatch: ...


@dataclass(frozen=True)
class ShadowRunEvidence:
    """The immutable evidence emitted by one prospective shadow run."""

    recorded_observations: int
    existing_observations: int
    reviews: int
    market_unavailable: int
    market_unavailable_items: tuple[MarketUnavailable, ...]
    decision_formed: bool
    terminal_exit_event_ids: tuple[str, ...]
    decision: ShadowDecision
    qualification: ShadowQualification
    evidence_path: Path


class CashMergerShadow:
    """Refresh sources, replay the ledger, decide, and persist one Evidence record."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._ledger = ShadowLedger(root / "ledger")

    def next_refresh_start(self, *, end: date) -> date:
        """Resume after the newest evidence window, or begin prospectively today."""

        covered_ends = tuple(
            date.fromisoformat(str(json.loads(path.read_text())["source_window"]["end"]))
            for path in (self._root / "evidence").glob("*.json")
        )
        if not covered_ends:
            return end
        return min(max(covered_ends) + timedelta(days=1), end)

    def run(
        self,
        *,
        source: ShadowEventSource,
        marks: ShadowMarkSource,
        start: date,
        end: date,
        as_of: datetime,
        capital: float,
    ) -> ShadowRunEvidence:
        active = tuple(
            state
            for state in self._ledger.states(as_of=as_of)
            if state.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}
        )
        refresh = source.refresh(start=start, end=end, active_events=active)
        write = self._ledger.record(refresh.observations)
        states = self._ledger.states(as_of=as_of)
        market = marks.load(states, as_of=as_of)
        previous = _formed_decision(self._root / "evidence", as_of, capital)
        decision_formed = previous is None
        decision = previous or FrozenQ70Policy().decide(
            self._ledger.events(as_of=as_of),
            market.marks,
            as_of=as_of,
            capital=capital,
        )
        terminal_exit_event_ids = _terminal_exits(decision, states)
        qualification = self._ledger.qualification(as_of=as_of)
        payload = {
            "schema_version": 1,
            "as_of": as_of.isoformat(),
            "source_window": {"start": start.isoformat(), "end": end.isoformat()},
            "recorded_observations": write.added,
            "existing_observations": write.existing,
            "source_reviews": [asdict(review) for review in refresh.reviews],
            "market_unavailable": [asdict(item) for item in market.unavailable],
            "decision_formed": decision_formed,
            "terminal_exit_event_ids": terminal_exit_event_ids,
            "decision": asdict(decision),
            "qualification": asdict(qualification),
        }
        encoded = canonical_bytes(payload)
        identity = hashlib.sha256(encoded).hexdigest()
        evidence_path = self._root / "evidence" / f"{identity}.json"
        write_once(evidence_path, encoded)
        return ShadowRunEvidence(
            recorded_observations=write.added,
            existing_observations=write.existing,
            reviews=len(refresh.reviews),
            market_unavailable=len(market.unavailable),
            market_unavailable_items=market.unavailable,
            decision_formed=decision_formed,
            terminal_exit_event_ids=terminal_exit_event_ids,
            decision=decision,
            qualification=qualification,
            evidence_path=evidence_path,
        )


def _formed_decision(
    evidence_dir: Path,
    as_of: datetime,
    capital: float,
) -> ShadowDecision | None:
    month = as_of.strftime("%Y-%m")
    matches: list[ShadowDecision] = []
    for path in evidence_dir.glob("*.json"):
        payload = json.loads(path.read_text())
        decision = payload.get("decision")
        if not payload.get("decision_formed") or not isinstance(decision, dict):
            continue
        if not str(decision.get("as_of", "")).startswith(month):
            continue
        if float(decision["capital"]) != capital:
            raise ValueError("shadow capital changed within a frozen decision month")
        matches.append(
            ShadowDecision(
                as_of=str(decision["as_of"]),
                capital=float(decision["capital"]),
                positions=tuple(ShadowPosition(**position) for position in decision["positions"]),
                estimated_commissions=float(decision["estimated_commissions"]),
                estimated_slippage=float(decision["estimated_slippage"]),
                cash_reserve=float(decision["cash_reserve"]),
            )
        )
    if len(matches) > 1:
        raise ValueError(f"multiple formed shadow decisions found for {month}")
    return matches[0] if matches else None


def _terminal_exits(
    decision: ShadowDecision,
    states: tuple[EventObservation, ...],
) -> tuple[str, ...]:
    status_by_event = {state.event_id: state.status for state in states}
    return tuple(
        position.event_id
        for position in decision.positions
        if status_by_event.get(position.event_id)
        in {EventStatus.COMPLETED, EventStatus.TERMINATED, EventStatus.REPLACED}
    )

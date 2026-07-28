"""One end-to-end prospective cash-merger research shadow run."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from .artifacts import canonical_bytes, write_once
from .edgar import SourceRefresh
from .ledger import (
    EventObservation,
    EventStatus,
    ShadowLedger,
    ShadowQualification,
)
from .market import MarketMarkBatch, MarketUnavailable
from .selection import (
    CashMergerSelector,
    SelectionAssessment,
    SelectionEngineIdentity,
    SelectionExclusion,
    SelectionExclusionReason,
    SelectionResult,
    ShadowDecision,
    ShadowPosition,
)

_EVIDENCE_SCHEMA_VERSION = 7


class ShadowEvidenceError(ValueError):
    """Persisted current-schema shadow evidence is malformed or ambiguous."""


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
    selection_formed: bool
    terminal_exit_event_ids: tuple[str, ...]
    selection: SelectionResult
    qualification: ShadowQualification
    evidence_path: Path


class CashMergerShadow:
    """Refresh sources, replay the ledger, decide, and persist one Evidence record."""

    def __init__(self, root: Path, selector: CashMergerSelector | None = None) -> None:
        self._root = root
        self._ledger = ShadowLedger(root / "ledger")
        self._selector = selector or CashMergerSelector()

    def next_refresh_start(self, *, end: date, bootstrap_start: date) -> date:
        """Resume after persisted evidence, or replay from an explicit first date."""

        if bootstrap_start > end:
            raise ValueError("shadow bootstrap start exceeds refresh end")

        covered_ends = tuple(
            date.fromisoformat(str(json.loads(path.read_text())["source_window"]["end"]))
            for path in (self._root / "evidence").glob("*.json")
        )
        if not covered_ends:
            return bootstrap_start
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
        previous = _formed_selection(
            self._root / "evidence",
            as_of,
            capital,
            engine=self._selector.engine_identity,
            decision_engine_id=self._selector.decision_engine_id,
        )
        selection_formed = previous is None
        selection = previous or self._selector.select(
            self._ledger.events(as_of=as_of),
            market.marks,
            as_of=as_of,
            capital=capital,
        )
        decision = selection.decision
        terminal_exit_event_ids = _terminal_exits(decision, states)
        qualification = self._ledger.qualification(as_of=as_of)
        payload = {
            "schema_version": _EVIDENCE_SCHEMA_VERSION,
            "as_of": as_of.isoformat(),
            "source_window": {"start": start.isoformat(), "end": end.isoformat()},
            "recorded_observations": write.added,
            "existing_observations": write.existing,
            "source_reviews": [asdict(review) for review in refresh.reviews],
            "market_unavailable": [asdict(item) for item in market.unavailable],
            "selection_formed": selection_formed,
            "terminal_exit_event_ids": terminal_exit_event_ids,
            "selection": asdict(selection),
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
            selection_formed=selection_formed,
            terminal_exit_event_ids=terminal_exit_event_ids,
            selection=selection,
            qualification=qualification,
            evidence_path=evidence_path,
        )


def _formed_selection(
    evidence_dir: Path,
    as_of: datetime,
    capital: float,
    *,
    engine: SelectionEngineIdentity,
    decision_engine_id: str,
) -> SelectionResult | None:
    month = as_of.strftime("%Y-%m")
    matches: list[SelectionResult] = []
    for path in sorted(evidence_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ShadowEvidenceError(f"cannot read shadow evidence {path}") from error
        if not isinstance(payload, dict):
            raise ShadowEvidenceError(f"malformed shadow evidence {path}")
        if payload.get("schema_version") != _EVIDENCE_SCHEMA_VERSION:
            continue
        selection = payload.get("selection")
        if payload.get("selection_formed") is False:
            continue
        if payload.get("selection_formed") is not True or not isinstance(
            selection, dict
        ):
            raise ShadowEvidenceError(f"malformed shadow evidence {path}")
        formed_selection = _decode_selection(selection, path=path)
        if not formed_selection.decision.as_of.startswith(month):
            continue
        if formed_selection.engine != engine:
            continue
        if formed_selection.decision_engine_id != decision_engine_id:
            continue
        if formed_selection.decision.capital != capital:
            raise ShadowEvidenceError(
                "shadow capital changed within a frozen selection month"
            )
        matches.append(formed_selection)
    if len(matches) > 1:
        raise ShadowEvidenceError(
            f"multiple formed shadow selections found for {month} and engine"
        )
    return matches[0] if matches else None


def _decode_selection(payload: dict[str, object], *, path: Path) -> SelectionResult:
    engine_payload = payload.get("engine")
    decision_payload = payload.get("decision")
    if not isinstance(engine_payload, dict) or not isinstance(decision_payload, dict):
        raise ShadowEvidenceError(f"malformed shadow evidence {path}")
    positions = _records(decision_payload, "positions", path=path)
    assessments = _records(payload, "assessments", path=path)
    exclusions = _records(payload, "exclusions", path=path)
    try:
        engine = SelectionEngineIdentity(
            engine_id=str(engine_payload["engine_id"]),
            model_artifact_id=str(engine_payload["model_artifact_id"]),
            training_cutoff=(
                str(engine_payload["training_cutoff"])
                if engine_payload["training_cutoff"] is not None
                else None
            ),
        )
        decision = ShadowDecision(
            as_of=str(decision_payload["as_of"]),
            capital=float(decision_payload["capital"]),
            positions=tuple(ShadowPosition(**position) for position in positions),
            estimated_base_commission=float(
                decision_payload["estimated_base_commission"]
            ),
            estimated_slippage=float(decision_payload["estimated_slippage"]),
            estimated_fx_conversion=float(
                decision_payload["estimated_fx_conversion"]
            ),
            cash_reserve=float(decision_payload["cash_reserve"]),
        )
        return SelectionResult(
            engine=engine,
            decision_engine_id=str(payload["decision_engine_id"]),
            assessments=tuple(SelectionAssessment(**assessment) for assessment in assessments),
            exclusions=tuple(
                SelectionExclusion(
                    event_id=str(exclusion["event_id"]),
                    instrument_id=str(exclusion["instrument_id"]),
                    ticker=str(exclusion["ticker"]),
                    reason=SelectionExclusionReason(exclusion["reason"]),
                )
                for exclusion in exclusions
            ),
            decision=decision,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ShadowEvidenceError(f"malformed shadow evidence {path}") from error


def _records(
    payload: Mapping[str, object],
    field: str,
    *,
    path: Path,
) -> tuple[dict[str, Any], ...]:
    records = payload.get(field)
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ShadowEvidenceError(f"malformed shadow evidence {path}")
    return cast(tuple[dict[str, Any], ...], tuple(records))


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

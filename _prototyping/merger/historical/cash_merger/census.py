"""Build one causal record per announced fixed-cash merger.

This module owns the census contract. Event discovery and reference providers may
change without changing callers, while the resulting deal tape remains immutable,
content-addressed, and explicit about measured coverage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Protocol

from research.aegis_research.external_data._snapshot_cache import (
    SnapshotCacheMiss,
    newest_covering,
)

EventStatus = Literal["pending", "completed", "terminated"]
DealOutcome = Literal["pending", "completed", "terminated"]


class CashMergerCensusIntegrityError(ValueError):
    """A census snapshot violates its content or causal identity."""


@dataclass(frozen=True)
class CashMergerEvent:
    """One fixed-cash deal fact at the instant it became public."""

    target_cik: str
    target_name: str
    target_symbol: str
    status: EventStatus
    available_at: str
    offer_price: float | None
    source_form: str
    source_url: str
    accession: str


@dataclass(frozen=True)
class ReferenceDeal:
    """One independently sourced deal eligible for the coverage denominator."""

    target_name: str
    acquirer_name: str
    source_url: str
    announced_on: date | None = None
    target_symbol: str | None = None


@dataclass(frozen=True)
class CashMergerDeal:
    """One announced deal assembled from its causal public observations."""

    deal_id: str
    target_cik: str
    target_name: str
    announcement_symbol: str
    announced_at: str
    initial_offer_price: float
    latest_offer_price: float
    outcome: DealOutcome
    resolved_at: str | None
    accessions: tuple[str, ...]
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class CoverageAudit:
    """Recall of the discovered tape against an independently eligible census."""

    reference_deals: int
    matched_reference_deals: int
    coverage: float
    unmatched_targets: tuple[str, ...]

    def passes(self, minimum_coverage: float) -> bool:
        if not 0.0 <= minimum_coverage <= 1.0:
            raise ValueError("minimum coverage must lie in [0, 1]")
        return self.reference_deals > 0 and self.coverage >= minimum_coverage


@dataclass(frozen=True)
class CashMergerCensusSnapshot:
    """Immutable deal census and the evidence needed to judge its completeness."""

    deals: tuple[CashMergerDeal, ...]
    audit: CoverageAudit
    retrieved_at: str
    covered_start: str
    covered_end: str
    source_sha256: str


class EventSource(Protocol):
    def events(self, start: date, end: date) -> Iterable[CashMergerEvent]: ...


class ReferenceSource(Protocol):
    def deals(self, start: date, end: date) -> Iterable[ReferenceDeal]: ...


@dataclass(frozen=True)
class CashMergerCensusSource:
    """Own fetch, assembly, audit, and immutable cache selection for the census."""

    cache_dir: Path
    events: EventSource
    references: ReferenceSource

    def sync(self, start: date, end: date) -> CashMergerCensusSnapshot:
        """Return a covering census, fetching atomically only on a cache miss."""

        if end < start:
            raise ValueError("cash-merger census end precedes start")
        try:
            return self.load(start, end)
        except SnapshotCacheMiss:
            return self._fetch(start, end)

    def load(self, start: date, end: date) -> CashMergerCensusSnapshot:
        """Read the newest validated covering census without network access."""

        return newest_covering(
            self.cache_dir.glob("cash-merger-census-*.json"),
            load_snapshot,
            start,
            end,
        )

    def _fetch(self, start: date, end: date) -> CashMergerCensusSnapshot:
        observations = tuple(
            sorted(
                (
                    event
                    for event in self.events.events(start, end)
                    if start.isoformat() <= event.available_at[:10] <= end.isoformat()
                ),
                key=lambda event: (event.available_at, event.target_cik, event.accession),
            )
        )
        deals = assemble_deals(observations)
        references = tuple(self.references.deals(start, end))
        audit = audit_coverage(deals, references)
        snapshot = _snapshot(deals, audit, start, end)
        payload = _snapshot_payload(snapshot)
        destination = self.cache_dir / (
            f"cash-merger-census-{payload['snapshot_sha256'][:16]}.json"
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        _write_once(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return snapshot


def assemble_deals(events: Iterable[CashMergerEvent]) -> tuple[CashMergerDeal, ...]:
    """Reduce causal events into separate lifecycle records without symbol leakage."""

    active: dict[str, list[CashMergerEvent]] = {}
    assembled: list[CashMergerDeal] = []
    ordered = sorted(
        events,
        key=lambda item: (
            item.available_at,
            item.target_cik,
            0 if item.status != "pending" else 1,
            item.accession,
        ),
    )
    for event in ordered:
        lifecycle = active.get(event.target_cik)
        if event.status == "pending":
            if lifecycle is None:
                active[event.target_cik] = [event]
            else:
                lifecycle.append(event)
            continue
        if lifecycle is None:
            continue
        lifecycle.append(event)
        assembled.append(_assemble_lifecycle(lifecycle))
        active.pop(event.target_cik)
    assembled.extend(_assemble_lifecycle(lifecycle) for lifecycle in active.values())
    return tuple(sorted(assembled, key=lambda deal: (deal.announced_at, deal.deal_id)))


def audit_coverage(
    deals: Iterable[CashMergerDeal], references: Iterable[ReferenceDeal]
) -> CoverageAudit:
    """Match an eligible reference census by target identity and announcement date."""

    discovered = tuple(deals)
    reference_rows = tuple(references)
    unmatched: list[str] = []
    matched = 0
    for reference in reference_rows:
        candidates = [deal for deal in discovered if _matches_reference(deal, reference)]
        if len(candidates) == 1:
            matched += 1
        else:
            unmatched.append(reference.target_name)
    count = len(reference_rows)
    return CoverageAudit(
        reference_deals=count,
        matched_reference_deals=matched,
        coverage=matched / count if count else 0.0,
        unmatched_targets=tuple(unmatched),
    )


def _matches_reference(deal: CashMergerDeal, reference: ReferenceDeal) -> bool:
    if reference.target_symbol is not None:
        return deal.outcome == "pending" and deal.announcement_symbol == reference.target_symbol
    if not _same_target(deal.target_name, reference.target_name):
        return False
    if reference.announced_on is None:
        return deal.outcome == "pending"
    announced_on = date.fromisoformat(deal.announced_at[:10])
    return abs((announced_on - reference.announced_on).days) <= 7


def _assemble_lifecycle(events: list[CashMergerEvent]) -> CashMergerDeal:
    first = events[0]
    pending = tuple(event for event in events if event.status == "pending")
    if not pending or first.offer_price is None:
        raise CashMergerCensusIntegrityError(
            "deal lifecycle must start with a priced pending event"
        )
    latest_price = next(
        event.offer_price for event in reversed(pending) if event.offer_price is not None
    )
    terminal = events[-1] if events[-1].status != "pending" else None
    return CashMergerDeal(
        deal_id=f"{first.target_cik}:{first.accession}",
        target_cik=first.target_cik,
        target_name=first.target_name,
        announcement_symbol=first.target_symbol,
        announced_at=first.available_at,
        initial_offer_price=first.offer_price,
        latest_offer_price=latest_price,
        outcome=terminal.status if terminal is not None else "pending",
        resolved_at=terminal.available_at if terminal is not None else None,
        accessions=tuple(event.accession for event in events),
        source_urls=tuple(event.source_url for event in events),
    )


def _same_target(left: str, right: str) -> bool:
    aliases = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited"}
    left_tokens = [token for token in _name_tokens(left) if token not in aliases]
    right_tokens = [token for token in _name_tokens(right) if token not in aliases]
    return left_tokens == right_tokens


def _name_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _snapshot(
    deals: tuple[CashMergerDeal, ...],
    audit: CoverageAudit,
    start: date,
    end: date,
) -> CashMergerCensusSnapshot:
    source_payload = {
        "deals": [asdict(deal) for deal in deals],
        "audit": asdict(audit),
    }
    source_sha256 = hashlib.sha256(_canonical_json(source_payload)).hexdigest()
    return CashMergerCensusSnapshot(
        deals=deals,
        audit=audit,
        retrieved_at=datetime.now(UTC).isoformat(),
        covered_start=start.isoformat(),
        covered_end=end.isoformat(),
        source_sha256=source_sha256,
    )


def _snapshot_payload(snapshot: CashMergerCensusSnapshot) -> dict[str, object]:
    identity_payload = {
        "covered_start": snapshot.covered_start,
        "covered_end": snapshot.covered_end,
        "deals": [asdict(deal) for deal in snapshot.deals],
        "audit": asdict(snapshot.audit),
    }
    return {
        "schema_version": 1,
        "snapshot_sha256": hashlib.sha256(_canonical_json(identity_payload)).hexdigest(),
        "source_sha256": snapshot.source_sha256,
        "retrieved_at": snapshot.retrieved_at,
        **identity_payload,
    }


def load_snapshot(path: Path) -> CashMergerCensusSnapshot:
    """Validate and load one immutable census snapshot."""

    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise CashMergerCensusIntegrityError("unsupported cash-merger census schema")
    identity_payload = {
        "covered_start": payload.get("covered_start"),
        "covered_end": payload.get("covered_end"),
        "deals": payload.get("deals"),
        "audit": payload.get("audit"),
    }
    identity = hashlib.sha256(_canonical_json(identity_payload)).hexdigest()
    if identity != payload.get("snapshot_sha256") or identity[:16] not in path.name:
        raise CashMergerCensusIntegrityError("census content does not match its identity")
    deals = tuple(
        CashMergerDeal(
            **{
                **item,
                "accessions": tuple(item["accessions"]),
                "source_urls": tuple(item["source_urls"]),
            }
        )
        for item in payload["deals"]
    )
    audit_payload = payload["audit"]
    audit = CoverageAudit(
        **{
            **audit_payload,
            "unmatched_targets": tuple(audit_payload["unmatched_targets"]),
        }
    )
    return CashMergerCensusSnapshot(
        deals=deals,
        audit=audit,
        retrieved_at=str(payload["retrieved_at"]),
        covered_start=str(payload["covered_start"]),
        covered_end=str(payload["covered_end"]),
        source_sha256=str(payload["source_sha256"]),
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _write_once(destination: Path, contents: str) -> None:
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(FileExistsError):
            os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

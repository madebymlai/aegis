"""Configured-universe cash-merger ingestion through free SEC EDGAR access."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from html import unescape
from typing import Protocol

from nautilus_trader.model.identifiers import InstrumentId

from .ledger import EventObservation, EventStatus
from .timeline import (
    CloseGuidance,
    DealTimelineEvidence,
    TimelineMilestone,
    TimelineMilestoneKind,
)

_EDGAR_IDENTITY = "Aegis research m@laimk.dev"
_MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        (
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
    )
    if name
}
_MERGER_FORMS = (
    "8-K",
    "8-K/A",
    "6-K",
    "6-K/A",
    "PREM14A",
    "DEFM14A",
    "DEFA14A",
    "SC 14D9",
    "SC 14D9/A",
    "SC TO-T",
    "SC TO-T/A",
)
_TIMELINE_FORMS = frozenset(_MERGER_FORMS) - {"8-K", "8-K/A"}
_TERMINAL_FORMS = frozenset({"8-K", "8-K/A", "6-K", "6-K/A"})


class EdgarSourceError(RuntimeError):
    """SEC EDGAR data cannot form a configured-universe observation."""


@dataclass(frozen=True)
class SourceReview:
    """A filing preserved for review because deterministic extraction failed."""

    accession: str
    cik: str
    ticker: str
    reason: str


@dataclass(frozen=True)
class SourceRefresh:
    """Causal observations and explicit rejections produced by one refresh."""

    observations: tuple[EventObservation, ...]
    reviews: tuple[SourceReview, ...]


@dataclass(frozen=True)
class IssuerIdentity:
    """One configured tradeable instrument resolved to its SEC issuer."""

    instrument_id: str
    ticker: str
    cik: str


@dataclass(frozen=True)
class EdgarFiling:
    """The filing facts needed by the merger-domain parser."""

    accession: str
    cik: str
    filed_at: datetime
    form: str
    source_url: str
    submission: bytes
    items: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()


class EdgarGateway(Protocol):
    def resolve(self, instrument_ids: tuple[str, ...]) -> tuple[IssuerIdentity, ...]: ...

    def filings(
        self,
        *,
        start: date,
        end: date,
        ciks: frozenset[str],
    ) -> tuple[EdgarFiling, ...]: ...


class EdgarToolsGateway:
    """Present EdgarTools as the narrow source interface required by the strategy."""

    def __init__(self) -> None:
        from edgar import set_identity, use_local_storage

        set_identity(_EDGAR_IDENTITY)
        use_local_storage()

    def resolve(self, instrument_ids: tuple[str, ...]) -> tuple[IssuerIdentity, ...]:
        from edgar import Company

        identities: list[IssuerIdentity] = []
        for value in instrument_ids:
            instrument_id = InstrumentId.from_str(value)
            ticker = instrument_id.symbol.value
            company = Company(ticker)
            identities.append(IssuerIdentity(str(instrument_id), ticker, str(company.cik)))
        return tuple(identities)

    def filings(
        self,
        *,
        start: date,
        end: date,
        ciks: frozenset[str],
    ) -> tuple[EdgarFiling, ...]:
        from edgar import Company

        filings: list[EdgarFiling] = []
        window = (start.isoformat(), end.isoformat())
        for cik in sorted(ciks):
            company_filings = Company(int(cik)).get_filings(
                form=list(_MERGER_FORMS),
                filing_date=window,
            )
            for filing in company_filings:
                accepted = filing.acceptance_datetime
                if accepted is None:
                    raise EdgarSourceError(
                        f"EDGAR filing {filing.accession_no} omitted acceptance_datetime"
                    )
                submission = filing.full_text_submission()
                if not submission:
                    raise EdgarSourceError(
                        f"EDGAR filing {filing.accession_no} omitted its complete submission"
                    )
                filings.append(
                    EdgarFiling(
                        accession=filing.accession_no,
                        cik=str(filing.cik),
                        filed_at=_as_utc(accepted),
                        form=filing.form,
                        source_url=filing.homepage_url,
                        submission=submission.encode(),
                        items=_items(filing.items),
                        document_types=tuple(
                            sorted(
                                {
                                    attachment.document_type.upper()
                                    for attachment in filing.attachments
                                }
                            )
                        ),
                    )
                )
        return tuple(sorted(filings, key=lambda item: (item.filed_at, item.accession)))


class EdgarEventSource:
    """Attach public merger filings only to configured tradeable instruments."""

    def __init__(
        self,
        instrument_ids: Iterable[str],
        *,
        gateway: EdgarGateway | None = None,
    ) -> None:
        self._instrument_ids = tuple(dict.fromkeys(instrument_ids))
        if not self._instrument_ids:
            raise EdgarSourceError("cash-merger universe must contain at least one InstrumentId")
        self._gateway = gateway or EdgarToolsGateway()
        self._resolved: tuple[IssuerIdentity, ...] | None = None

    def refresh(
        self,
        *,
        start: date,
        end: date,
        active_events: Iterable[EventObservation],
    ) -> SourceRefresh:
        if end < start:
            raise ValueError("EDGAR refresh end precedes start")
        identities = self._identities()
        by_cik = {identity.cik: identity for identity in identities}
        configured_ids = {identity.instrument_id for identity in identities}
        active = tuple(
            event
            for event in active_events
            if event.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}
            and event.instrument_id in configured_ids
        )
        filings = tuple(
            filing
            for filing in self._gateway.filings(
                start=start,
                end=end,
                ciks=frozenset(by_cik),
            )
            if filing.cik in by_cik
        )
        original_active_by_cik = _active_by_cik(active)
        observations: list[EventObservation] = []
        reviews: list[SourceReview] = []
        for filing in _unique_filings(filings):
            if not _opens_agreement(filing):
                continue
            observation, review = _announcement(filing, by_cik[filing.cik])
            if observation is not None:
                known_active = (
                    *original_active_by_cik.get(observation.target_cik, ()),
                    *(
                        item
                        for item in observations
                        if item.target_cik == observation.target_cik
                        and item.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}
                    ),
                )
                observations.append(
                    _preserve_event_identity(
                        observation,
                        known_active,
                    )
                )
            if review is not None:
                reviews.append(review)
        lifecycle_events = _latest_active((*active, *observations))
        if lifecycle_events:
            lifecycle_by_cik = _active_by_cik(lifecycle_events)
            announcements_by_accession = _announcements_by_accession(observations)
            for filing in _unique_filings(filings):
                if not _could_change_lifecycle(filing):
                    continue
                cik = filing.cik
                candidates = _lifecycle_candidates(
                    filing,
                    announcements_by_accession,
                    original_active_by_cik.get(cik, ()),
                    lifecycle_by_cik.get(cik, ()),
                )
                if not candidates:
                    continue
                observation, review = _lifecycle(
                    filing,
                    candidates,
                )
                if observation is not None:
                    observations.append(observation)
                if review is not None:
                    reviews.append(review)
        return SourceRefresh(
            observations=tuple(
                sorted(observations, key=lambda item: (item.observed_at, item.event_id))
            ),
            reviews=tuple(sorted(reviews, key=lambda item: (item.accession, item.reason))),
        )

    def _identities(self) -> tuple[IssuerIdentity, ...]:
        if self._resolved is None:
            resolved = self._gateway.resolve(self._instrument_ids)
            if {identity.instrument_id for identity in resolved} != set(self._instrument_ids):
                raise EdgarSourceError("EDGAR identity resolution did not cover the configured universe")
            by_cik: dict[str, IssuerIdentity] = {}
            for identity in resolved:
                previous = by_cik.get(identity.cik)
                if previous is not None and previous.instrument_id != identity.instrument_id:
                    raise EdgarSourceError(
                        f"configured instruments {previous.instrument_id} and "
                        f"{identity.instrument_id} resolve to the same CIK {identity.cik}"
                    )
                by_cik[identity.cik] = identity
            self._resolved = tuple(sorted(resolved, key=lambda item: item.instrument_id))
        return self._resolved


def _opens_agreement(filing: EdgarFiling) -> bool:
    return "EX-2.1" in filing.document_types or "EX-2.1" in _documents(filing.submission)


def _could_change_lifecycle(filing: EdgarFiling) -> bool:
    document_types = set(filing.document_types) or set(_documents(filing.submission))
    return bool(
        filing.form.upper() in _TIMELINE_FORMS
        or set(filing.items).intersection({"1.02", "2.01", "8.01"})
        or "EX-2.1" in document_types
    )


def _latest_active(events: Iterable[EventObservation]) -> tuple[EventObservation, ...]:
    latest: dict[str, EventObservation] = {}
    for event in sorted(events, key=lambda item: (item.observed_at, item.source_accession)):
        if event.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}:
            latest[event.event_id] = event
    return tuple(latest[event_id] for event_id in sorted(latest))


def _announcements_by_accession(
    observations: Iterable[EventObservation],
) -> dict[str, tuple[EventObservation, ...]]:
    grouped: dict[str, list[EventObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.source_accession, []).append(observation)
    return {accession: tuple(events) for accession, events in grouped.items()}


def _lifecycle_candidates(
    filing: EdgarFiling,
    announcements_by_accession: dict[str, tuple[EventObservation, ...]],
    original_active: tuple[EventObservation, ...],
    all_active: tuple[EventObservation, ...],
) -> tuple[EventObservation, ...]:
    accession = filing.accession
    same_filing_announcements = announcements_by_accession.get(accession)
    if same_filing_announcements is None:
        return all_active
    if not original_active:
        return ()
    old_dates = {event.agreement_date for event in original_active}
    opens_different_agreement = any(
        event.agreement_date not in old_dates for event in same_filing_announcements
    )
    return original_active if opens_different_agreement else ()


def _preserve_event_identity(
    observation: EventObservation,
    active_events: tuple[EventObservation, ...],
) -> EventObservation:
    same_agreement = {
        event.event_id: event
        for event in active_events
        if event.agreement_date == observation.agreement_date
    }
    if not same_agreement:
        return observation
    if len(same_agreement) > 1:
        raise EdgarSourceError(
            f"multiple active events share agreement date {observation.agreement_date}"
        )
    event = next(iter(same_agreement.values()))
    return replace(
        observation,
        event_id=event.event_id,
        agreement_accession=event.agreement_accession,
        status=EventStatus.AMENDED,
    )


def _announcement(
    filing: EdgarFiling,
    identity: IssuerIdentity,
) -> tuple[EventObservation | None, SourceReview | None]:
    accession = filing.accession
    cik = filing.cik
    ticker = identity.ticker
    documents = _documents(filing.submission)
    agreement = " ".join(documents.get("EX-2.1", ()))
    disclosure = " ".join(
        text
        for document_type, texts in documents.items()
        if document_type == "8-K" or document_type.startswith("EX-99")
        for text in texts
    )
    agreement_date = _agreement_date(agreement)
    if agreement_date is None:
        return None, SourceReview(accession, cik, ticker, "agreement date not extracted")
    offer = _cash_offer(agreement, disclosure)
    if offer is None:
        return None, SourceReview(accession, cik, ticker, "unique fixed-cash offer not extracted")
    return (
        EventObservation(
            event_id=f"{cik}:{accession}",
            instrument_id=identity.instrument_id,
            target_cik=cik,
            ticker=ticker,
            agreement_accession=accession,
            agreement_date=agreement_date.isoformat(),
            observed_at=filing.filed_at.isoformat(),
            status=EventStatus.ANNOUNCED,
            offer_price=offer,
            source_accession=accession,
            source_url=filing.source_url,
            evidence=f"Agreement dated {agreement_date.isoformat()}; fixed cash ${offer:.4f}",
            timeline=_timeline_evidence(f"{disclosure} {agreement}"),
        ),
        None,
    )


def _lifecycle(
    filing: EdgarFiling,
    active_events: tuple[EventObservation, ...],
) -> tuple[EventObservation | None, SourceReview | None]:
    accession = filing.accession
    cik = filing.cik
    documents = _documents(filing.submission)
    text = " ".join(value for values in documents.values() for value in values)
    matching = tuple(event for event in active_events if _agreement_is_identified(text, event))
    if len(matching) != 1:
        if filing.form.upper() in _TIMELINE_FORMS:
            return None, None
        return None, SourceReview(
            accession,
            cik,
            active_events[0].ticker if active_events else "",
            "filing does not identify the active agreement",
        )
    event = matching[0]
    completed = _completion_disclosure(filing, text)
    terminated = _termination_disclosure(filing, text)
    if completed is not None:
        status = EventStatus.COMPLETED
        evidence = completed.group(0)
    elif terminated is not None:
        new_agreement_date = _agreement_date(" ".join(documents.get("EX-2.1", ())))
        status = (
            EventStatus.REPLACED
            if new_agreement_date is not None
            and new_agreement_date.isoformat() != event.agreement_date
            else EventStatus.TERMINATED
        )
        evidence = terminated.group(0)
    else:
        timeline = _timeline_evidence(text)
        if timeline is not None:
            return (
                EventObservation(
                    event_id=event.event_id,
                    instrument_id=event.instrument_id,
                    target_cik=event.target_cik,
                    ticker=event.ticker,
                    agreement_accession=event.agreement_accession,
                    agreement_date=event.agreement_date,
                    observed_at=filing.filed_at.isoformat(),
                    status=EventStatus.AMENDED,
                    offer_price=event.offer_price,
                    source_accession=accession,
                    source_url=filing.source_url,
                    evidence="Causal deal-timeline terms updated.",
                    timeline=timeline,
                ),
                None,
            )
        if filing.form.upper() in _TIMELINE_FORMS:
            return None, None
        return None, SourceReview(
            accession,
            cik,
            event.ticker,
            "identified agreement has no deterministic terminal state",
        )
    return (
        EventObservation(
            event_id=event.event_id,
            instrument_id=event.instrument_id,
            target_cik=event.target_cik,
            ticker=event.ticker,
            agreement_accession=event.agreement_accession,
            agreement_date=event.agreement_date,
            observed_at=filing.filed_at.isoformat(),
            status=status,
            offer_price=event.offer_price,
            source_accession=accession,
            source_url=filing.source_url,
            evidence=evidence,
        ),
        None,
    )


def _completion_disclosure(
    filing: EdgarFiling,
    text: str,
) -> re.Match[str] | None:
    if not _terminal_item(filing, {"2.01", "8.01"}):
        return None
    return re.search(
        r"(?:completed|consummated|closed)\s+(?:the\s+)?(?:merger|transaction)|"
        r"(?:merger|transaction)\s+(?:was\s+)?(?:completed|consummated|closed)",
        text,
        re.I,
    )


def _termination_disclosure(
    filing: EdgarFiling,
    text: str,
) -> re.Match[str] | None:
    if not _terminal_item(filing, {"1.02", "8.01"}):
        return None
    return re.search(
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)"
        r".{0,160}?\b(?:has\s+been|was|were)\s+(?:validly\s+)?terminated\b|"
        r"\b(?:company|parent|parties|board)\b.{0,160}?\bterminated\b.{0,160}?"
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)|"
        r"\bentered\s+into\b.{0,120}?\btermination\s+agreement\b.{0,160}?"
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)",
        text,
        re.I,
    )


def _terminal_item(filing: EdgarFiling, allowed_items: set[str]) -> bool:
    form = filing.form.upper()
    if form not in _TERMINAL_FORMS:
        return False
    if form in {"6-K", "6-K/A"}:
        return True
    return bool(set(filing.items).intersection(allowed_items))


def _timeline_evidence(text: str) -> DealTimelineEvidence | None:
    guidance = _close_guidance(text)
    outside_date = _outside_date(text)
    milestones = _milestones(text)
    if guidance is None and outside_date is None and not milestones:
        return None
    return DealTimelineEvidence(
        guidance=guidance,
        outside_date=outside_date.isoformat() if outside_date is not None else None,
        milestones=milestones,
    )


def _close_guidance(text: str) -> CloseGuidance | None:
    quarter = re.search(
        r"\b(?:expected|expect)\b.{0,80}?"
        r"\b(?:clos(?:e|ed|ing)|complet(?:e|ed|ion))\b\s+"
        r"(?:in|during|by\s+(?:the\s+)?end\s+of)\s+(?:the\s+)?"
        r"(first|second|third|fourth|[1-4](?:st|nd|rd|th)?|q[1-4])\s+quarter"
        r"(?:\s+of)?\s+(?:calendar\s+year\s+)?(20\d{2})",
        text,
        re.I,
    )
    if quarter is not None:
        number = _quarter_number(quarter[1])
        year = int(quarter[2])
        start_month = 3 * (number - 1) + 1
        end_month = start_month + 2
        earliest = date(year, start_month, 1)
        latest = date(year + (end_month == 12), end_month % 12 + 1, 1) - timedelta(days=1)
        return CloseGuidance(earliest.isoformat(), latest.isoformat())
    half = re.search(
        r"\b(?:expected|expect)\b.{0,80}?"
        r"\b(?:clos(?:e|ed|ing)|complet(?:e|ed|ion))\b\s+"
        r"(?:in|during)\s+(?:the\s+)?"
        r"(first|second)\s+half(?:\s+of)?\s+"
        r"(?:calendar\s+year\s+)?(20\d{2})",
        text,
        re.I,
    )
    if half is not None:
        year = int(half[2])
        if half[1].lower() == "first":
            return CloseGuidance(f"{year}-01-01", f"{year}-06-30")
        return CloseGuidance(f"{year}-07-01", f"{year}-12-31")
    late_to_early = re.search(
        r"\b(?:expected|expect)\b.{0,80}?"
        r"\b(?:clos(?:e|ed|ing)|complet(?:e|ed|ion))\b\s+in\s+"
        r"late\s+(20\d{2})\s+or\s+early\s+(20\d{2})",
        text,
        re.I,
    )
    if late_to_early is not None:
        early_year = int(late_to_early[1])
        late_year = int(late_to_early[2])
        if late_year == early_year + 1:
            return CloseGuidance(f"{early_year}-10-01", f"{late_year}-03-31")
    mid_year = re.search(
        r"\b(?:expected|expect)\b.{0,80}?"
        r"\b(?:clos(?:e|ed|ing)|complet(?:e|ed|ion))\b\s+"
        r"(?:is\s+|in\s+)?mid\s*-\s*(20\d{2})",
        text,
        re.I,
    )
    if mid_year is not None:
        year = int(mid_year[1])
        return CloseGuidance(f"{year}-04-01", f"{year}-09-30")
    return None


def _outside_date(text: str) -> date | None:
    relative = re.search(
        r"date\s+that\s+is\s+(\d{1,3})\s+days\s+after\s+"
        r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})\s*"
        r"\(\s*(?:the\s+)?[\"“”']?\s*outside\s+date",
        text,
        re.I,
    )
    if relative is not None:
        month = _MONTHS.get(relative[2].lower())
        if month is None:
            return None
        outside_date = date(int(relative[4]), month, int(relative[3])) + timedelta(
            days=int(relative[1])
        )
        return _extend_outside_date(
            outside_date,
            text[relative.end() : relative.end() + 320],
        )
    match = re.search(
        r"(?:outside|termination|end)\s+date\s+(?:means|shall\s+be|is)\s+"
        r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})",
        text,
        re.I,
    )
    if match is None:
        match = re.search(
            r"(?:merger|transaction).{0,160}?"
            r"(?:consummated|completed|closed).{0,120}?\bon\s+"
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2}).{0,180}?"
            r"(?:the\s+)?[\"“”']?\s*outside\s+date",
            text,
            re.I,
        )
    if match is None:
        match = re.search(
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})\s*"
            r"\(\s*(?:the\s+)?[\"“”']?\s*outside\s+date",
            text,
            re.I,
        )
    if match is None:
        return None
    rendered_outside_date = _rendered_date(match)
    if rendered_outside_date is None:
        return None
    return _extend_outside_date(
        rendered_outside_date,
        text[match.end() : match.end() + 320],
    )


def _extend_outside_date(outside_date: date, extension: str) -> date:
    exact_extensions = tuple(
        rendered
        for extension_match in re.finditer(
            r"\bto\s+([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})",
            extension,
            re.I,
        )
        if (rendered := _rendered_date(extension_match)) is not None
    )
    if exact_extensions:
        outside_date = max(outside_date, *exact_extensions)
    day_extension = re.search(
        r"(?:up\s+to\s+|single\s+)?(\d{1,3})(?:[-\s]+)days?",
        extension,
        re.I,
    )
    if day_extension is not None:
        outside_date += timedelta(days=int(day_extension[1]))
    month_extension = re.search(
        r"(?:period\s+of\s+|up\s+to\s+)?(?:[A-Za-z]+\s+)?"
        r"\(?(\d{1,2})\)?(?:[-\s]+)months?",
        extension,
        re.I,
    )
    if month_extension is not None:
        outside_date = _add_months(outside_date, int(month_extension[1]))
    return outside_date


def _milestones(text: str) -> tuple[TimelineMilestone, ...]:
    patterns = (
        (
            TimelineMilestoneKind.SHAREHOLDER_VOTE,
            r"(?:special\s+)?meeting\s+of\s+(?:the\s+)?(?:company'?s\s+)?"
            r"(?:stockholders|shareholders).{0,120}?(?:held|scheduled)\s+(?:on|for)\s+"
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2}).{0,160}?\bvote\b",
        ),
        (
            TimelineMilestoneKind.TENDER_EXPIRATION,
            r"(?:offer|tender\s+offer).{0,120}?\bexpire(?:s|d)?\b.{0,80}?"
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})",
        ),
    )
    milestones: list[TimelineMilestone] = []
    for kind, pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match is None:
            continue
        scheduled_for = _rendered_date(match)
        if scheduled_for is not None:
            milestones.append(TimelineMilestone(kind, scheduled_for.isoformat()))
    return tuple(milestones)


def _rendered_date(match: re.Match[str]) -> date | None:
    month = _MONTHS.get(match[1].lower())
    if month is None:
        return None
    return date(int(match[3]), month, int(match[2]))


def _quarter_number(value: str) -> int:
    normalized = value.lower()
    names = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    if normalized in names:
        return names[normalized]
    number = re.search(r"[1-4]", normalized)
    if number is None:
        raise EdgarSourceError(f"unsupported closing quarter {value}")
    return int(number[0])


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def _agreement_is_identified(text: str, event: EventObservation) -> bool:
    agreement_date = date.fromisoformat(event.agreement_date)
    rendered = f"{agreement_date.strftime('%B')} {agreement_date.day}, {agreement_date.year}"
    positions = (match.start() for match in re.finditer(re.escape(rendered), text, re.I))
    return any(
        re.search(
            r"merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger",
            text[max(0, position - 240) : position + 240],
            re.I,
        )
        is not None
        for position in positions
    )


def _active_by_cik(
    active_events: tuple[EventObservation, ...],
) -> dict[str, tuple[EventObservation, ...]]:
    grouped: dict[str, list[EventObservation]] = {}
    for event in active_events:
        grouped.setdefault(event.target_cik, []).append(event)
    return {
        cik: tuple(sorted(events, key=lambda item: item.event_id))
        for cik, events in grouped.items()
    }


def _documents(submission: bytes) -> dict[str, tuple[str, ...]]:
    raw = submission.decode("utf-8", errors="replace")
    grouped: dict[str, list[str]] = {}
    for block in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", raw, re.I | re.S):
        type_match = re.search(r"<TYPE>\s*([^\r\n<]+)", block, re.I)
        text_match = re.search(r"<TEXT>(.*?)</TEXT>", block, re.I | re.S)
        if type_match is None or text_match is None:
            continue
        grouped.setdefault(type_match.group(1).strip().upper(), []).append(
            _plain(text_match.group(1))
        )
    return {key: tuple(values) for key, values in grouped.items()}


def _agreement_date(text: str) -> date | None:
    match = re.search(
        r"agreement\s+and\s+plan\s+of\s+merger.{0,160}?"
        r"(?:dated|as\s+of)\s+([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})",
        text,
        re.I,
    )
    if match is None:
        return None
    month = _MONTHS.get(match[1].lower())
    if month is None:
        return None
    return date(int(match[3]), month, int(match[2]))


def _cash_offer(agreement: str, disclosure: str) -> float | None:
    combined = f"{disclosure} {agreement}"
    patterns = (
        r"right\s+to\s+receive\s+\$([0-9]+(?:\.[0-9]+)?)"
        r"(?:\s+per\s+(?:share|common\s+share|common\s+unit))?"
        r"(?:,?\s+net)?\s+in\s+cash",
        r"right\s+to\s+receive\s+cash\s+in\s+an?\s+amount\s+"
        r"(?:equal\s+to\s+)?\$([0-9]+(?:\.[0-9]+)?)",
        r"\$([0-9]+(?:\.[0-9]+)?)\s+per\s+"
        r"(?:share|common\s+share|common\s+unit)"
        r"(?:,?\s+net)?\s+in\s+(?:cash|an?\s+all-cash\s+transaction)",
    )
    prices: set[float] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, combined, re.I):
            if _has_nearby_non_cash_consideration(combined, match):
                continue
            price = float(match[1])
            if 0.01 <= price <= 10_000.00:
                prices.add(price)
    return next(iter(prices)) if len(prices) == 1 else None


def _has_nearby_non_cash_consideration(text: str, cash_match: re.Match[str]) -> bool:
    variable = (
        r"(?:[0-9]+(?:\.[0-9]+)?\s+)?(?:buyer\s+)?shares?\b|"
        r"stock\s+consideration|common\s+stock|ordinary\s+shares?|"
        r"contingent\s+value\s+rights?|\bCVRs?\b"
    )
    before = text[max(0, cash_match.start() - 600) : cash_match.start()]
    after = text[cash_match.end() : cash_match.end() + 600]
    stock_before_cash = re.search(
        rf"(?:{variable}).{{0,500}}\bplus\b\s*$|"
        rf"(?:{variable}).{{0,120}}\band\b\s*$",
        before,
        re.I,
    )
    stock_after_cash = re.search(
        rf"\bplus\b.{{0,500}}(?:{variable})|"
        rf"^\s*(?:,\s*)?(?:without\s+interest\s*)?\band\b.{{0,120}}(?:{variable})",
        after,
        re.I,
    )
    return stock_before_cash is not None or stock_after_cash is not None


def _unique_filings(filings: Iterable[EdgarFiling]) -> tuple[EdgarFiling, ...]:
    by_accession = {filing.accession: filing for filing in filings}
    return tuple(by_accession[accession] for accession in sorted(by_accession))


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value))).strip()


def _as_utc(stamp: datetime) -> datetime:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _items(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),)

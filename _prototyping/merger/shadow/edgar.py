"""Configured-universe cash-merger ingestion through free SEC EDGAR access."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from html import unescape
from typing import Protocol

from nautilus_trader.model.identifiers import InstrumentId

from .ledger import EventObservation, EventStatus

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
                form=["8-K", "8-K/A"],
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
                observations.append(
                    _preserve_event_identity(
                        observation,
                        original_active_by_cik.get(observation.target_cik, ()),
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
    return bool(set(filing.items).intersection({"1.02", "2.01"}) or "EX-2.1" in document_types)


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
    same_agreement = tuple(
        event for event in active_events if event.agreement_date == observation.agreement_date
    )
    if not same_agreement:
        return observation
    if len(same_agreement) > 1:
        raise EdgarSourceError(
            f"multiple active events share agreement date {observation.agreement_date}"
        )
    event = same_agreement[0]
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
        return None, SourceReview(
            accession,
            cik,
            active_events[0].ticker if active_events else "",
            "filing does not identify the active agreement",
        )
    event = matching[0]
    completed = re.search(
        r"(?:completed|consummated|closed)\s+(?:the\s+)?(?:merger|transaction)|"
        r"(?:merger|transaction)\s+(?:was\s+)?(?:completed|consummated|closed)",
        text,
        re.I,
    )
    terminated = re.search(
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)"
        r".{0,160}?\b(?:has\s+been|was|were)\s+(?:validly\s+)?terminated\b|"
        r"\b(?:company|parent|parties|board)\b.{0,160}?\bterminated\b.{0,160}?"
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)|"
        r"\bentered\s+into\b.{0,120}?\btermination\s+agreement\b.{0,160}?"
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)",
        text,
        re.I,
    )
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

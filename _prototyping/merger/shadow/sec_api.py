"""Dynamic SEC-API ingestion with immutable, idempotent source snapshots."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from html import unescape
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

from .artifacts import (
    canonical_bytes,
    write_gzip_once,
    write_once,
)
from .ledger import EventObservation, EventStatus

_QUERY_URL = "https://api.sec-api.io"
_ARCHIVE_URL = "https://archive.sec-api.io/{cik}/{numeric}/{accession}.txt"
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


class SecApiCredentialsError(RuntimeError):
    """The prospective source cannot refresh without an SEC-API credential."""


class SecApiResponseError(RuntimeError):
    """SEC-API returned a response that cannot form causal observations."""


class SecApiTransport(Protocol):
    def query(self, request: bytes) -> bytes: ...

    def submission(self, cik: str, accession: str) -> bytes: ...


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


class SecApiHttpTransport:
    """Own authenticated SEC-API requests; callers see only immutable bytes."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("SEC_API_KEY")
        if not self._api_key:
            raise SecApiCredentialsError("SEC_API_KEY is required on a cold source refresh")

    def query(self, request: bytes) -> bytes:
        return _request(
            _QUERY_URL,
            request,
            api_key=self._api_key,
            method="POST",
            content_type="application/json",
        )

    def submission(self, cik: str, accession: str) -> bytes:
        numeric = accession.replace("-", "")
        return _request(
            _ARCHIVE_URL.format(cik=cik, numeric=numeric, accession=accession),
            None,
            api_key=self._api_key,
            method="GET",
            content_type=None,
        )


class SecApiSource:
    """Discover prospective fixed-cash filings and replay a warm cache offline."""

    def __init__(self, cache_dir: Path, *, transport: SecApiTransport | None = None) -> None:
        self._cache_dir = cache_dir
        self._transport = transport

    def refresh(
        self,
        *,
        start: date,
        end: date,
        active_events: Iterable[EventObservation],
    ) -> SourceRefresh:
        if end < start:
            raise ValueError("SEC-API refresh end precedes start")
        active = tuple(
            event
            for event in active_events
            if event.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}
        )
        announcement_filings = self._query(_announcement_query(start, end))
        original_active_by_cik = _active_by_cik(active)
        observations: list[EventObservation] = []
        reviews: list[SourceReview] = []
        for filing in _unique_filings(announcement_filings):
            submission = self._submission(filing)
            observation, review = _announcement(filing, submission)
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
            lifecycle_filings = self._query(_lifecycle_query(start, end, lifecycle_events))
            for filing in _unique_filings(lifecycle_filings):
                if not _could_change_lifecycle(filing):
                    continue
                cik = _required_text(filing, "cik")
                candidates = _lifecycle_candidates(
                    filing,
                    announcements_by_accession,
                    original_active_by_cik.get(cik, ()),
                    lifecycle_by_cik.get(cik, ()),
                )
                if not candidates:
                    continue
                submission = self._submission(filing)
                observation, review = _lifecycle(
                    filing,
                    submission,
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

    def _query(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        page_size = int(request["size"])
        filings: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_request = {**request, "from": str(offset)}
            page, total = self._query_page(page_request)
            filings.extend(page)
            offset += len(page)
            if not page or offset >= total:
                return filings
            if len(page) < page_size:
                raise SecApiResponseError(
                    "SEC-API Query returned an incomplete page before its reported total"
                )

    def _query_page(self, request: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        request_bytes = canonical_bytes(request)
        request_identity = hashlib.sha256(request_bytes).hexdigest()
        cached = _cached_query(self._cache_dir / "queries", request_identity)
        if cached is None:
            response = self._network().query(request_bytes)
            parsed = _query_payload(response)
            _store_query(
                self._cache_dir / "queries",
                request_identity=request_identity,
                response=response,
            )
            return parsed
        return _query_payload(cached)

    def _submission(self, filing: dict[str, Any]) -> bytes:
        accession = _required_text(filing, "accessionNo")
        cached = tuple((self._cache_dir / "submissions").glob(f"{accession}-*.txt.gz"))
        if len(cached) > 1:
            raise SecApiResponseError(f"conflicting cached submissions for {accession}")
        if cached:
            with gzip.open(cached[0], "rb") as handle:
                return handle.read()
        cik = _required_text(filing, "cik")
        response = self._network().submission(cik, accession)
        if b"<SEC-DOCUMENT" not in response and b"<SEC-HEADER" not in response:
            raise SecApiResponseError(f"SEC-API omitted the complete submission for {accession}")
        identity = hashlib.sha256(response).hexdigest()
        destination = self._cache_dir / "submissions" / f"{accession}-{identity}.txt.gz"
        write_gzip_once(destination, response)
        return response

    def _network(self) -> SecApiTransport:
        if self._transport is None:
            self._transport = SecApiHttpTransport()
        return self._transport


def _announcement_query(start: date, end: date) -> dict[str, Any]:
    return {
        "query": (
            'formType:"8-K" AND documentFormatFiles.type:"EX-2.1" '
            f"AND filedAt:[{start.isoformat()} TO {end.isoformat()}]"
        ),
        "from": "0",
        "size": "50",
        "sort": [{"filedAt": {"order": "asc"}}],
    }


def _lifecycle_query(
    start: date,
    end: date,
    active_events: tuple[EventObservation, ...],
) -> dict[str, Any]:
    ciks = ", ".join(sorted({event.target_cik for event in active_events}))
    return {
        "query": (
            f'cik:({ciks}) AND formType:"8-K" '
            f"AND filedAt:[{start.isoformat()} TO {end.isoformat()}]"
        ),
        "from": "0",
        "size": "50",
        "sort": [{"filedAt": {"order": "asc"}}],
    }


def _could_change_lifecycle(filing: dict[str, Any]) -> bool:
    items = {str(item) for item in filing.get("items") or ()}
    document_types = {
        str(document.get("type") or "").upper()
        for document in filing.get("documentFormatFiles") or ()
        if isinstance(document, dict)
    }
    return bool(items.intersection({"1.01", "1.02", "2.01"}) or "EX-2.1" in document_types)


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
    filing: dict[str, Any],
    announcements_by_accession: dict[str, tuple[EventObservation, ...]],
    original_active: tuple[EventObservation, ...],
    all_active: tuple[EventObservation, ...],
) -> tuple[EventObservation, ...]:
    accession = _required_text(filing, "accessionNo")
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
        raise SecApiResponseError(
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
    filing: dict[str, Any], submission: bytes
) -> tuple[EventObservation | None, SourceReview | None]:
    accession = _required_text(filing, "accessionNo")
    cik = _required_text(filing, "cik")
    ticker = _ticker(filing)
    documents = _documents(submission)
    agreement = " ".join(documents.get("EX-2.1", ()))
    disclosure = " ".join(
        text
        for document_type, texts in documents.items()
        if document_type == "8-K" or document_type.startswith("EX-99")
        for text in texts
    )
    if not ticker:
        return None, SourceReview(accession, cik, "", "missing point-in-time ticker")
    agreement_date = _agreement_date(agreement)
    if agreement_date is None:
        return None, SourceReview(accession, cik, ticker, "agreement date not extracted")
    offer = _cash_offer(agreement, disclosure)
    if offer is None:
        return None, SourceReview(accession, cik, ticker, "unique fixed-cash offer not extracted")
    filed_at = _utc_iso(_required_text(filing, "filedAt"))
    source_url = str(filing.get("linkToFilingDetails") or "")
    return (
        EventObservation(
            event_id=f"{cik}:{accession}",
            target_cik=cik,
            ticker=ticker,
            agreement_accession=accession,
            agreement_date=agreement_date.isoformat(),
            observed_at=filed_at,
            status=EventStatus.ANNOUNCED,
            offer_price=offer,
            source_accession=accession,
            source_url=source_url,
            evidence=f"Agreement dated {agreement_date.isoformat()}; fixed cash ${offer:.4f}",
        ),
        None,
    )


def _lifecycle(
    filing: dict[str, Any],
    submission: bytes,
    active_events: tuple[EventObservation, ...],
) -> tuple[EventObservation | None, SourceReview | None]:
    accession = _required_text(filing, "accessionNo")
    cik = _required_text(filing, "cik")
    ticker = _ticker(filing)
    documents = _documents(submission)
    text = " ".join(value for values in documents.values() for value in values)
    matching = tuple(event for event in active_events if _agreement_is_identified(text, event))
    if len(matching) != 1:
        return None, SourceReview(
            accession,
            cik,
            ticker,
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
        r"(?:terminated|termination).{0,180}(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger)|"
        r"(?:merger\s+agreement|agreement\s+and\s+plan\s+of\s+merger).{0,180}(?:terminated|termination)",
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
            ticker,
            "identified agreement has no deterministic terminal state",
        )
    return (
        EventObservation(
            event_id=event.event_id,
            target_cik=event.target_cik,
            ticker=event.ticker,
            agreement_accession=event.agreement_accession,
            agreement_date=event.agreement_date,
            observed_at=_utc_iso(_required_text(filing, "filedAt")),
            status=status,
            offer_price=event.offer_price,
            source_accession=accession,
            source_url=str(filing.get("linkToFilingDetails") or ""),
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
    if re.search(
        r"exchange\s+ratio|stock\s+consideration|contingent\s+value\s+right|\bCVR\b", combined, re.I
    ):
        return None
    patterns = (
        r"\$([0-9]+(?:\.[0-9]+)?)\s+per\s+(?:share|common\s+unit)\s+in\s+cash",
        r"right\s+to\s+receive\s+\$([0-9]+(?:\.[0-9]+)?)\s+per\s+(?:share|common\s+unit)\s+in\s+cash",
    )
    prices = {
        float(match[1])
        for pattern in patterns
        for match in re.finditer(pattern, combined, re.I)
        if 0.01 <= float(match[1]) <= 10_000.00
    }
    return next(iter(prices)) if len(prices) == 1 else None


def _unique_filings(filings: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    by_accession = {_required_text(filing, "accessionNo"): filing for filing in filings}
    return tuple(by_accession[accession] for accession in sorted(by_accession))


def _query_payload(response: bytes) -> tuple[list[dict[str, Any]], int]:
    try:
        payload = json.loads(response)
    except json.JSONDecodeError as error:
        raise SecApiResponseError("SEC-API Query returned invalid JSON") from error
    filings = payload.get("filings")
    if not isinstance(filings, list):
        raise SecApiResponseError("SEC-API Query omitted filings")
    total = payload.get("total")
    if not isinstance(total, dict) or not isinstance(total.get("value"), int):
        raise SecApiResponseError("SEC-API Query omitted total.value")
    if total["value"] < len(filings):
        raise SecApiResponseError("SEC-API Query total is smaller than its filing page")
    return filings, total["value"]


def _cached_query(directory: Path, request_identity: str) -> bytes | None:
    matches: list[tuple[str, bytes]] = []
    for path in directory.glob("*.json"):
        payload = json.loads(path.read_text())
        if payload.get("request_sha256") == request_identity:
            matches.append((str(payload["retrieved_at"]), canonical_bytes(payload["response"])))
    return max(matches)[1] if matches else None


def _store_query(directory: Path, *, request_identity: str, response: bytes) -> None:
    parsed = json.loads(response)
    response_identity = hashlib.sha256(canonical_bytes(parsed)).hexdigest()
    envelope = {
        "request_sha256": request_identity,
        "response_sha256": response_identity,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "response": parsed,
    }
    write_once(
        directory / f"{request_identity}-{response_identity}.json",
        canonical_bytes(envelope),
    )


def _request(
    url: str,
    body: bytes | None,
    *,
    api_key: str,
    method: str,
    content_type: str | None,
) -> bytes:
    headers = {"Authorization": api_key, "Accept-Encoding": "identity"}
    if content_type is not None:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        payload = response.read()
        return (
            gzip.decompress(payload)
            if response.headers.get("Content-Encoding", "").lower() == "gzip"
            else payload
        )


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or not str(value).strip():
        raise SecApiResponseError(f"SEC-API filing omitted {key}")
    return str(value).strip()


def _ticker(filing: dict[str, Any]) -> str:
    value = filing.get("ticker")
    if isinstance(value, list):
        return str(value[0]).upper() if value else ""
    return str(value or "").upper()


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value))).strip()


def _utc_iso(value: str) -> str:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).isoformat()

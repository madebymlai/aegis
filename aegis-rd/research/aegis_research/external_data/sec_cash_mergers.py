"""Point-in-time fixed-cash merger events sourced from SEC EDGAR filings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import warnings
from calendar import month_abbr, month_name, monthrange
from collections.abc import Iterable, Iterator
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Protocol

import requests

from research.aegis_research.external_data._snapshot_cache import newest_covering, sync_on_miss

_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
_ARCHIVE_URL = "https://www.sec.gov/Archives/{path}"
_SEC_USER_AGENT = "Aegis Research m@laimk.dev"
_DISCOVERY_FORMS = frozenset({"DEFM14A", "SC 14D9", "SC 14D9/A"})
_FOLLOW_UP_FORMS = frozenset({"8-K", "8-K/A", "DEFA14A", "DEFM14A"})
_ANNOUNCEMENT_FORMS = frozenset({"8-K"})
_ANNOUNCEMENT_FILING_WINDOW_DAYS = 4
_SYMBOL_FORMS = frozenset({"8-K", "10-K", "10-Q"})
_SYMBOL_LOOKBACK_DAYS = 370
_DEFINITIVE = re.compile(
    r"agreement\s+and\s+plan\s+of\s+merger|definitive\s+(?:merger\s+)?agreement", re.I
)
_CASH = re.compile(r"(?:per\s+share\s+)?in\s+cash|cash\s+consideration", re.I)
_TERMINATED = re.compile(
    r"(?:"
    r"(?:the\s+)?(?:parties|company|parent|purchaser|buyer|seller)\s+"
    r"(?:has\s+|have\s+)?terminated\s+(?:the\s+)?merger\s+agreement"
    r"|(?:the\s+)?merger\s+agreement\s+(?:has\s+been|was)\s+terminated"
    r"|item\s+1\.02.{0,160}?termination\s+of\s+a\s+material\s+definitive\s+agreement"
    r")",
    re.I,
)
_COMPLETED = re.compile(
    r"(?:completed|consummated)\s+(?:the\s+)?merger|became\s+(?:a\s+)?wholly[- ]owned\s+subsidiary",
    re.I,
)
_OFFER_PATTERNS = (
    re.compile(
        r"(?:agreement|transaction).{0,300}?\$\s*(\d{1,4}(?:\.\d{1,4})?)\s+"
        r"(?:in\s+cash\s+per\s+share|per\s+share\s+in\s+cash)",
        re.I,
    ),
    re.compile(
        r"(?:agreement|transaction).{0,500}?(?:at|for)\s+(?:a\s+)?"
        r"(?:purchase\s+)?price\s+of\s+\$\s*(\d{1,4}(?:\.\d{1,4})?)"
        r"\s+per\s+share\s+in\s+cash",
        re.I,
    ),
    re.compile(
        r"(?:acquire|purchase).{0,500}?(?:all|any).{0,200}?"
        r"(?:shares?|common\s+stock).{0,300}?"
        r"(?:at|for)\s+(?:a\s+)?(?:purchase\s+)?price\s+of\s+\$\s*"
        r"(\d{1,4}(?:\.\d{1,4})?)\s+per\s+share\s+in\s+cash",
        re.I,
    ),
    re.compile(
        r"(?:offer|merger)\s+price\s+of\s+\$\s*(\d{1,4}(?:\.\d{1,4})?)"
        r"\s+per\s+share",
        re.I,
    ),
    re.compile(
        r"(?:each|every)[^.]{0,160}?shares?[^.]{0,300}?"
        r"(?:converted\s+into[^.]{0,100}?(?:right\s+to\s+)?receive|"
        r"(?:right\s+to\s+)?receive)[^.]{0,100}?\$\s*"
        r"(\d{1,4}(?:\.\d{1,4})?)[^.]{0,40}?(?:\bin\s+cash\b|\bper\s+share\b)",
        re.I,
    ),
    re.compile(
        r"holders?[^.]{0,160}?\breceive\s+\$\s*(\d{1,4}(?:\.\d{1,4})?)"
        r"\s+in\s+cash\s+(?:for\s+each|per)\s+share",
        re.I,
    ),
    re.compile(
        r"(?:revised\s+)?(?:per[- ]share\s+)?cash\s+consideration\s+"
        r"(?:is|of)\s+\$\s*(\d{1,4}(?:\.\d{1,4})?)",
        re.I,
    ),
)
_NON_CASH_CONSIDERATION = re.compile(
    r"(?:"
    r"shares?\s+of\s+[^.]{0,160}?(?:common\s+)?stock[^.]{0,160}?(?:and|plus)"
    r"[^.]{0,120}?\$"
    r"|\$\s*\d[^.]{0,100}?(?:and|plus)\s+[^.]{0,160}?shares?\s+of\s+"
    r"[^.]{0,80}?(?:common\s+)?stock"
    r"|exchange\s+ratio"
    r"|stock\s+consideration"
    r"|amount\s+of\s+stock\s+per"
    r"|contingent\s+value\s+rights?"
    r"|\bCVRs?\b"
    r")",
    re.I,
)
_COMPLEX_MERGER_SUMMARY = re.compile(
    r"(?:stock[- ]and[- ]cash|exchange\s+ratio|stock\s+consideration|"
    r"contingent\s+value\s+rights?|\bCVRs?\b)",
    re.I,
)


class CashMergerSourceError(RuntimeError):
    """The live EDGAR source and validated cache cannot satisfy a request."""


class CashMergerIntegrityError(ValueError):
    """A cached event snapshot does not match its content identity."""


@dataclass(frozen=True)
class SecFiling:
    """One filing document as observed by EDGAR at its public filing timestamp."""

    accession: str
    cik: str
    company_name: str
    symbol: str
    form: str
    filed_at: str
    source_url: str
    text: str


@dataclass(frozen=True)
class CashMergerEvent:
    """One causal state change in a target's fixed-cash merger lifecycle."""

    target_cik: str
    target_name: str
    target_symbol: str
    status: str
    available_at: str
    offer_price: float | None
    expected_close: str | None
    source_form: str
    source_url: str
    accession: str

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_resolution(self) -> bool:
        return self.status in {"completed", "terminated"}

    @property
    def is_announcement_filing(self) -> bool:
        return self.is_pending and self.source_form in _ANNOUNCEMENT_FORMS


@dataclass(frozen=True)
class CashMergerSnapshot:
    events: tuple[CashMergerEvent, ...]
    source_sha256: str
    retrieved_at: str
    covered_start: str
    covered_end: str


class FilingClient(Protocol):
    def filings(self, start: date, end: date) -> Iterable[SecFiling]: ...


@dataclass(frozen=True)
class _MasterIndexRow:
    cik: str
    company_name: str
    form: str
    filed_on: date
    archive_path: str


@dataclass(frozen=True)
class _ObservedFiling:
    row: _MasterIndexRow
    text: str
    filed_at: str


@dataclass(frozen=True)
class _ClassifiedFiling:
    observed: _ObservedFiling
    filing: SecFiling
    event: CashMergerEvent


@dataclass(frozen=True)
class _DiscoveredDeal:
    agreement_date: date | None


@dataclass(frozen=True)
class _CausalReplay:
    filings: tuple[SecFiling, ...]
    candidate_events: int


class _EdgarArchive:
    """Own SEC request pacing, retries, and bounded filing-document reuse."""

    def __init__(self, session: requests.Session, client: EdgarMasterIndexClient) -> None:
        self._session = session
        self._client = client
        self._last_request_at = 0.0
        self._documents: dict[str, str] = {}

    def index(self, year: int, quarter: int) -> str | None:
        response = self._get(_INDEX_URL.format(year=year, quarter=quarter))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.text

    def document(self, archive_path: str) -> str:
        cached = self._documents.get(archive_path)
        if cached is not None:
            return cached
        response = self._get(_ARCHIVE_URL.format(path=archive_path))
        response.raise_for_status()
        if len(self._documents) == 16:
            self._documents.pop(next(iter(self._documents)))
        self._documents[archive_path] = response.text
        return response.text

    def _get(self, url: str) -> requests.Response:
        for attempt in range(self._client.max_retries + 1):
            wait = self._client.minimum_request_interval_seconds - (
                time.monotonic() - self._last_request_at
            )
            if wait > 0.0:
                time.sleep(wait)
            response = self._session.get(url, timeout=self._client.timeout_seconds)
            self._last_request_at = time.monotonic()
            if response.status_code not in {429, 503} or attempt == self._client.max_retries:
                return response
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    delay = float(retry_after)
                except ValueError:
                    warnings.warn(
                        f"SEC returned invalid Retry-After header {retry_after!r}",
                        stacklevel=2,
                    )
                else:
                    time.sleep(delay)
                    continue
            time.sleep(min(2.0**attempt, 30.0))
        raise AssertionError("unreachable EDGAR retry loop")


@dataclass(frozen=True)
class EdgarMasterIndexClient:
    """Read a causal merger subset from EDGAR's official master indexes.

    Definitive proxy and target-recommendation filings identify candidate CIKs.
    Only those targets' current reports are then replayed from the announcement,
    supplying the original terms, amendments, and resolutions without downloading
    every historical 8-K or relying on today's survivor ticker map. Completed
    quarters are immutable; SEC updates the current full index through the previous
    business day, which matches the scheduled ingestion cadence.
    """

    timeout_seconds: int = 30
    minimum_request_interval_seconds: float = 0.20
    max_retries: int = 5

    def filings(self, start: date, end: date) -> Iterator[SecFiling]:
        headers = {"User-Agent": _SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        lookup_start = start - timedelta(days=_SYMBOL_LOOKBACK_DAYS)
        with requests.Session() as session:
            session.headers.update(headers)
            archive = _EdgarArchive(session, self)
            rows = _master_index_rows(archive, lookup_start, end)
            yield from _causal_merger_filings(rows, archive, start, end)


@dataclass(frozen=True)
class SecCashMergerEventSource:
    """Own EDGAR fetch, causal parsing, validation, and immutable cache selection."""

    cache_dir: Path
    client: FilingClient | None = None

    def sync(self, start: date, end: date) -> None:
        """Ensure the cache covers the requested range, fetching only on a miss."""

        sync_on_miss(lambda: self.load(start, end), lambda: self._fetch(start, end))

    def load(self, start: date, end: date) -> CashMergerSnapshot:
        """Read a validated covering tape without contacting EDGAR."""

        return newest_covering(
            self.cache_dir.glob("cash-merger-events-*.json"),
            load_snapshot,
            start,
            end,
        )

    def _fetch(self, start: date, end: date) -> None:
        if end < start:
            raise ValueError("cash-merger event range end precedes start")
        client = self.client or EdgarMasterIndexClient()
        events = tuple(
            sorted(
                filter(None, (_event_from_filing(filing) for filing in client.filings(start, end))),
                key=lambda event: (event.available_at, event.target_cik, event.accession),
            )
        )
        if not events:
            raise CashMergerSourceError(
                f"EDGAR returned no fixed-cash merger events for {start} through {end}"
            )
        snapshot = _snapshot(events, start=start, end=end)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = _snapshot_payload(snapshot)
        destination = _cached_snapshot_path(self.cache_dir, snapshot)
        _write_once(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _event_from_filing(filing: SecFiling) -> CashMergerEvent | None:
    primary_document = _primary_document(filing.text, filing.form)
    if primary_document is None:
        return None
    text = _plain_text(primary_document)
    pending = _DEFINITIVE.search(text) and _CASH.search(text)
    if _TERMINATED.search(text):
        status = "terminated"
        offer_price = None
    elif _COMPLETED.search(text):
        status = "completed"
        offer_price = None
    elif pending:
        if _COMPLEX_MERGER_SUMMARY.search(text[:100_000]) is not None:
            return None
        status = "pending"
        offer_price = _offer_price(text)
        if offer_price is None:
            return None
    else:
        return None
    return CashMergerEvent(
        target_cik=filing.cik,
        target_name=filing.company_name,
        target_symbol=filing.symbol,
        status=status,
        available_at=_utc_iso(filing.filed_at),
        offer_price=offer_price,
        expected_close=_expected_close(text),
        source_form=filing.form,
        source_url=filing.source_url,
        accession=filing.accession,
    )


def _offer_price(text: str) -> float | None:
    for pattern in _OFFER_PATTERNS:
        for match in pattern.finditer(text):
            value = float(match.group(1))
            context = text[max(0, match.start() - 300) : match.end() + 200]
            if 0.01 <= value <= 10_000 and _NON_CASH_CONSIDERATION.search(context) is None:
                return value
    return None


def _primary_document(submission: str, form: str) -> str | None:
    documents = re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", submission, re.I | re.S)
    if not documents:
        return submission
    normalized_form = form.upper().replace(" ", "")
    for document in documents:
        type_match = re.search(r"<TYPE>\s*([^<\r\n]+)", document, re.I)
        if type_match is None:
            continue
        document_type = type_match.group(1).strip().upper().replace(" ", "")
        if document_type != normalized_form:
            continue
        text_match = re.search(r"<TEXT>(.*?)</TEXT>", document, re.I | re.S)
        return text_match.group(1) if text_match is not None else document
    return None


def _plain_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(text)))


def _expected_close(text: str) -> str | None:
    match = re.search(
        r"expected\s+to\s+close[^.]{0,120}?(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",
        text,
        re.I,
    )
    if match is None:
        return None
    year, month, day = (int(value) for value in match.groups())
    with suppress(ValueError):
        return date(year, month, day).isoformat()
    return None


def _agreement_date(filing: SecFiling) -> date | None:
    primary_document = _primary_document(filing.text, filing.form)
    if primary_document is None:
        return None
    text = _plain_text(primary_document)
    month_date = (
        r"(?:January|February|March|April|May|June|July|August|September|October|"
        r"November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|"
        r"Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+\d{1,2},\s+20\d{2}"
    )
    patterns = (
        rf"\bon\s+({month_date})[^.]{{0,300}}?entered\s+into[^.]{{0,200}}?"
        r"agreement\s+and\s+plan\s+of\s+merger",
        r"agreement\s+and\s+plan\s+of\s+merger[^.]{0,120}?"
        rf"(?:dated|as\s+of)\s+({month_date})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match is None:
            continue
        date_parts = re.fullmatch(
            r"([A-Za-z]+)\.?\s+(\d{1,2}),\s+(20\d{2})",
            match.group(1),
        )
        if date_parts is None:
            continue
        month_text, day_text, year_text = date_parts.groups()
        months = {name.lower(): number for number, name in enumerate(month_name) if name}
        months.update({name.lower(): number for number, name in enumerate(month_abbr) if name})
        months["sept"] = 9
        month = months.get(month_text.lower())
        day = int(day_text)
        year = int(year_text)
        if month is not None and 1 <= day <= monthrange(year, month)[1]:
            return date(year, month, day)
    return None


def _quarters(start: date, end: date) -> Iterator[tuple[int, int]]:
    year = start.year
    quarter = (start.month - 1) // 3 + 1
    end_quarter = (end.month - 1) // 3 + 1
    while (year, quarter) <= (end.year, end_quarter):
        yield year, quarter
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1


def _master_index_rows(
    archive: _EdgarArchive, start: date, end: date
) -> tuple[_MasterIndexRow, ...]:
    rows: list[_MasterIndexRow] = []
    for year, quarter in _quarters(start, end):
        index = archive.index(year, quarter)
        if index is not None:
            rows.extend(_index_rows(index))
    return tuple(rows)


def _causal_merger_filings(
    rows: tuple[_MasterIndexRow, ...],
    archive: _EdgarArchive,
    start: date,
    end: date,
) -> Iterator[SecFiling]:
    event_rows = tuple(
        row
        for row in rows
        if row.form in _DISCOVERY_FORMS | _FOLLOW_UP_FORMS and start <= row.filed_on <= end
    )
    symbol_rows = _symbol_rows_by_cik(rows, start - timedelta(days=_SYMBOL_LOOKBACK_DAYS), end)
    discoveries, classified_by_path = _discover_deals(event_rows, archive, symbol_rows)
    observations = _candidate_observations(event_rows, archive, discoveries, classified_by_path)
    replay = _replay_deal_filings(
        observations,
        archive,
        symbol_rows,
        discoveries,
        classified_by_path,
    )
    if replay.candidate_events and not replay.filings:
        raise CashMergerSourceError(
            "EDGAR merger candidates were found, but no point-in-time trading "
            "symbols could be resolved"
        )
    yield from replay.filings


def _discover_deals(
    event_rows: tuple[_MasterIndexRow, ...],
    archive: _EdgarArchive,
    symbol_rows: dict[str, tuple[_MasterIndexRow, ...]],
) -> tuple[dict[str, _DiscoveredDeal], dict[str, _ClassifiedFiling]]:
    discoveries: dict[str, _DiscoveredDeal] = {}
    classified_by_path: dict[str, _ClassifiedFiling] = {}
    for row in event_rows:
        if row.form not in _DISCOVERY_FORMS:
            continue
        observed = _observe_filing(row, archive)
        classified = _classify_filing(observed, archive, symbol_rows, {})
        if classified is None or not classified.event.is_pending:
            continue
        classified_by_path[row.archive_path] = classified
        existing = discoveries.get(row.cik)
        discoveries[row.cik] = _DiscoveredDeal(
            agreement_date=(
                existing.agreement_date
                if existing and existing.agreement_date
                else _agreement_date(classified.filing)
            ),
        )
    return discoveries, classified_by_path


def _candidate_observations(
    event_rows: tuple[_MasterIndexRow, ...],
    archive: _EdgarArchive,
    discoveries: dict[str, _DiscoveredDeal],
    classified_by_path: dict[str, _ClassifiedFiling],
) -> tuple[_ObservedFiling, ...]:
    observations = [classified.observed for classified in classified_by_path.values()]
    observations.extend(
        _observe_filing(row, archive)
        for row in event_rows
        if row.cik in discoveries and row.archive_path not in classified_by_path
    )
    return tuple(sorted(observations, key=lambda item: (item.filed_at, item.row.archive_path)))


def _replay_deal_filings(
    observations: tuple[_ObservedFiling, ...],
    archive: _EdgarArchive,
    symbol_rows: dict[str, tuple[_MasterIndexRow, ...]],
    discoveries: dict[str, _DiscoveredDeal],
    classified_by_path: dict[str, _ClassifiedFiling],
) -> _CausalReplay:
    active_symbols: dict[str, str] = {}
    resolved_ciks: set[str] = set()
    candidate_events = 0
    emitted_filings: list[SecFiling] = []
    for observed in observations:
        classified = classified_by_path.get(observed.row.archive_path)
        if classified is None or observed.row.cik in active_symbols:
            classified = _classify_filing(observed, archive, symbol_rows, active_symbols)
        if classified is None:
            continue
        filing = classified.filing
        event = classified.event
        cik = filing.cik
        if cik in resolved_ciks:
            continue
        if not _belongs_to_discovered_deal(filing, event, discoveries[cik]):
            continue
        if event.is_resolution and cik not in active_symbols:
            continue
        candidate_events += 1
        if not filing.symbol:
            continue
        if event.is_pending:
            active_symbols[cik] = filing.symbol
        elif event.is_resolution:
            active_symbols.pop(cik, None)
            resolved_ciks.add(cik)
        emitted_filings.append(filing)
    return _CausalReplay(tuple(emitted_filings), candidate_events)


def _classify_filing(
    observed: _ObservedFiling,
    archive: _EdgarArchive,
    symbol_rows: dict[str, tuple[_MasterIndexRow, ...]],
    active_symbols: dict[str, str],
) -> _ClassifiedFiling | None:
    filing = _causal_filing(observed, archive, symbol_rows, active_symbols)
    event = _event_from_filing(filing)
    if event is None:
        return None
    return _ClassifiedFiling(observed=observed, filing=filing, event=event)


def _belongs_to_discovered_deal(
    filing: SecFiling,
    event: CashMergerEvent,
    discovery: _DiscoveredDeal,
) -> bool:
    if event.source_form in _DISCOVERY_FORMS:
        return True
    if discovery.agreement_date is None:
        return False
    if event.is_announcement_filing:
        announcement_date = datetime.fromisoformat(event.available_at).date()
        return (
            discovery.agreement_date
            <= announcement_date
            <= discovery.agreement_date + timedelta(days=_ANNOUNCEMENT_FILING_WINDOW_DAYS)
        )
    return _agreement_date(filing) == discovery.agreement_date


def _symbol_rows_by_cik(
    rows: tuple[_MasterIndexRow, ...], start: date, end: date
) -> dict[str, tuple[_MasterIndexRow, ...]]:
    grouped: dict[str, list[_MasterIndexRow]] = {}
    for row in rows:
        if row.form in _SYMBOL_FORMS and start <= row.filed_on <= end:
            grouped.setdefault(row.cik, []).append(row)
    return {
        cik: tuple(sorted(items, key=lambda item: (item.filed_on, item.archive_path)))
        for cik, items in grouped.items()
    }


def _causal_filing(
    observed: _ObservedFiling,
    archive: _EdgarArchive,
    symbol_rows: dict[str, tuple[_MasterIndexRow, ...]],
    active_symbols: dict[str, str],
) -> SecFiling:
    row = observed.row
    symbol = active_symbols.get(row.cik)
    if symbol is None:
        symbol = _preceding_symbol(row.cik, observed.filed_at, symbol_rows, archive)
    if symbol is None:
        symbol = _trading_symbol(observed.text)
    return SecFiling(
        accession=Path(row.archive_path).stem,
        cik=row.cik,
        company_name=row.company_name,
        symbol=symbol or "",
        form=row.form,
        filed_at=observed.filed_at,
        source_url=_ARCHIVE_URL.format(path=row.archive_path),
        text=observed.text,
    )


def _observe_filing(row: _MasterIndexRow, archive: _EdgarArchive) -> _ObservedFiling:
    text = archive.document(row.archive_path)
    filed_at = _utc_iso(_acceptance_timestamp(text, row.filed_on.isoformat()))
    return _ObservedFiling(row=row, text=text, filed_at=filed_at)


def _preceding_symbol(
    cik: str,
    available_at: str,
    symbol_rows: dict[str, tuple[_MasterIndexRow, ...]],
    archive: _EdgarArchive,
) -> str | None:
    candidates: list[tuple[str, str, str]] = []
    filing_available_at = _utc_iso(available_at)
    for row in symbol_rows.get(cik, ()):
        text = archive.document(row.archive_path)
        observed_at = _utc_iso(_acceptance_timestamp(text, row.filed_on.isoformat()))
        if observed_at > filing_available_at:
            continue
        symbol = _trading_symbol(text)
        if symbol is not None:
            candidates.append((observed_at, row.archive_path, symbol))
    return max(candidates)[2] if candidates else None


def _acceptance_timestamp(text: str, filed_on: str) -> str:
    match = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", text, re.I)
    if match is None:
        return f"{filed_on}T00:00:00+00:00"
    stamp = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return stamp.isoformat()


def _cached_snapshot_path(cache_dir: Path, snapshot: CashMergerSnapshot) -> Path:
    identity = str(_snapshot_payload(snapshot)["snapshot_sha256"])
    return cache_dir / f"cash-merger-events-{identity[:16]}.json"


def _trading_symbol(text: str) -> str | None:
    xbrl_patterns = (
        r"name=[\"']dei:(?:Entity)?TradingSymbol[\"'][^>]*>\s*(?:<[^>]+>\s*)*([A-Z][A-Z0-9.-]{0,9})",
        r"<dei:(?:Entity)?TradingSymbol[^>]*>\s*([A-Z][A-Z0-9.-]{0,9})\s*</",
    )
    for pattern in xbrl_patterns:
        match = re.search(pattern, text, re.I)
        if match is not None:
            return match.group(1).upper()
    plain_text = _plain_text(text)
    prose_patterns = (
        r"\bunder\s+(?:the\s+)?(?:ticker\s+)?symbol\s+[\"'“”]?([A-Z][A-Z0-9.-]{0,9})\b",
        r"\bticker\s+symbol\s+(?:is\s+)?[\"'“”]?([A-Z][A-Z0-9.-]{0,9})\b",
    )
    for pattern in prose_patterns:
        match = re.search(pattern, plain_text, re.I)
        if match is not None:
            return match.group(1).upper()
    return None


def _index_rows(text: str) -> Iterator[_MasterIndexRow]:
    for line in text.splitlines():
        fields = line.split("|")
        if len(fields) != 5 or not fields[0].isdigit():
            continue
        yield _MasterIndexRow(
            cik=fields[0],
            company_name=fields[1],
            form=fields[2],
            filed_on=date.fromisoformat(fields[3]),
            archive_path=fields[4],
        )


def _utc_iso(value: str) -> str:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).isoformat()


def _snapshot(events: tuple[CashMergerEvent, ...], *, start: date, end: date) -> CashMergerSnapshot:
    observations = [asdict(event) for event in events]
    source_hash = hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CashMergerSnapshot(
        events=events,
        source_sha256=source_hash,
        retrieved_at=datetime.now(UTC).isoformat(),
        covered_start=start.isoformat(),
        covered_end=end.isoformat(),
    )


def _snapshot_payload(snapshot: CashMergerSnapshot) -> dict[str, object]:
    observations = [asdict(event) for event in snapshot.events]
    identity_payload = {
        "covered_start": snapshot.covered_start,
        "covered_end": snapshot.covered_end,
        "observations": observations,
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "snapshot_sha256": identity,
        "source_sha256": snapshot.source_sha256,
        "retrieved_at": snapshot.retrieved_at,
        "covered_start": snapshot.covered_start,
        "covered_end": snapshot.covered_end,
        "observations": observations,
    }


def load_snapshot(path: Path) -> CashMergerSnapshot:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise CashMergerIntegrityError("unsupported cash-merger snapshot schema")
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise CashMergerIntegrityError("cash-merger snapshot observations must be a list")
    identity_payload = {
        "covered_start": payload.get("covered_start"),
        "covered_end": payload.get("covered_end"),
        "observations": observations,
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if identity != payload.get("snapshot_sha256") or identity[:16] not in path.name:
        raise CashMergerIntegrityError("cash-merger snapshot content does not match its identity")
    events = tuple(CashMergerEvent(**item) for item in observations)
    if (
        tuple(
            sorted(
                events, key=lambda event: (event.available_at, event.target_cik, event.accession)
            )
        )
        != events
    ):
        raise CashMergerIntegrityError("cash-merger events must be ordered causally")
    return CashMergerSnapshot(
        events=events,
        source_sha256=str(payload["source_sha256"]),
        retrieved_at=str(payload["retrieved_at"]),
        covered_start=str(payload["covered_start"]),
        covered_end=str(payload["covered_end"]),
    )


def _write_once(destination: Path, contents: str) -> None:
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", text=True
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

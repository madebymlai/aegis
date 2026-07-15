"""Point-in-time fixed-cash merger events sourced from SEC EDGAR filings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import warnings
from collections.abc import Iterable, Iterator
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

import requests

_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
_ARCHIVE_URL = "https://www.sec.gov/Archives/{path}"
_DISCOVERY_FORMS = frozenset({"DEFM14A", "SC 14D9", "SC 14D9/A"})
_FOLLOW_UP_FORMS = frozenset({"8-K", "8-K/A", "DEFA14A", "DEFM14A"})
_DEFINITIVE = re.compile(r"agreement\s+and\s+plan\s+of\s+merger|definitive\s+(?:merger\s+)?agreement", re.I)
_CASH = re.compile(r"(?:per\s+share\s+)?in\s+cash|cash\s+consideration", re.I)
_TERMINATED = re.compile(r"terminat(?:ed|ion)\s+(?:of\s+)?(?:the\s+)?merger\s+agreement", re.I)
_COMPLETED = re.compile(
    r"(?:completed|consummated)\s+(?:the\s+)?merger|became\s+(?:a\s+)?wholly[- ]owned\s+subsidiary",
    re.I,
)
_OFFER_PATTERNS = (
    re.compile(r"\$\s*(\d{1,4}(?:\.\d{1,4})?)\s+(?:in\s+cash\s+)?per\s+share", re.I),
    re.compile(r"per[- ]share\s+(?:cash\s+)?consideration\s+of\s+\$\s*(\d{1,4}(?:\.\d{1,4})?)", re.I),
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
class EdgarDailyIndexClient:
    """Read a causal merger subset from EDGAR's quarterly master indexes.

    Definitive proxy and target-recommendation filings discover a target. Later
    current reports for that CIK supply amendments and resolutions. This avoids
    scanning every historical 8-K and never relies on today's survivor ticker map.
    """

    user_agent: str
    timeout_seconds: int = 30
    minimum_request_interval_seconds: float = 0.20
    max_retries: int = 5

    @classmethod
    def from_environment(cls) -> EdgarDailyIndexClient:
        user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
        if not user_agent:
            raise CashMergerSourceError(
                "SEC_USER_AGENT is required for live EDGAR access (for example, "
                "'Name email@example.com')"
            )
        return cls(user_agent=user_agent)

    def filings(self, start: date, end: date) -> Iterator[SecFiling]:
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        rows: list[tuple[str, str, str, str, str]] = []
        relevant_forms = _DISCOVERY_FORMS | _FOLLOW_UP_FORMS
        with requests.Session() as session:
            session.headers.update(headers)
            last_request_at = 0.0

            def get(url: str) -> requests.Response:
                nonlocal last_request_at
                for attempt in range(self.max_retries + 1):
                    wait = self.minimum_request_interval_seconds - (
                        time.monotonic() - last_request_at
                    )
                    if wait > 0.0:
                        time.sleep(wait)
                    response = session.get(url, timeout=self.timeout_seconds)
                    last_request_at = time.monotonic()
                    if response.status_code not in {429, 503}:
                        return response
                    if attempt == self.max_retries:
                        return response
                    retry_after = response.headers.get("Retry-After")
                    with suppress(TypeError, ValueError):
                        if retry_after is not None:
                            time.sleep(float(retry_after))
                            continue
                    delay = min(2.0**attempt, 30.0)
                    time.sleep(delay)
                raise AssertionError("unreachable EDGAR retry loop")

            for year, quarter in _quarters(start, end):
                index_url = _INDEX_URL.format(year=year, quarter=quarter)
                response = get(index_url)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                rows.extend(
                    row
                    for row in _index_rows(response.text)
                    if row[2] in relevant_forms
                    and start <= date.fromisoformat(row[3]) <= end
                )

            tracked_symbols: dict[str, str] = {}
            for cik, name, form, filed_on, archive_path in sorted(
                rows, key=lambda row: (row[3], row[4])
            ):
                if form not in _DISCOVERY_FORMS and cik not in tracked_symbols:
                    continue
                source_url = _ARCHIVE_URL.format(path=archive_path)
                response = get(source_url)
                response.raise_for_status()
                text = response.text
                symbol = tracked_symbols.get(cik) or _trading_symbol(text)
                if symbol is None:
                    continue
                filing = SecFiling(
                    accession=Path(archive_path).stem,
                    cik=cik,
                    company_name=name,
                    symbol=symbol,
                    form=form,
                    filed_at=_acceptance_timestamp(text, filed_on),
                    source_url=source_url,
                    text=text,
                )
                event = _event_from_filing(filing)
                if event is not None and event.status == "pending":
                    tracked_symbols[cik] = symbol
                yield filing


@dataclass(frozen=True)
class SecCashMergerEventSource:
    """Own EDGAR fetch, causal parsing, validation, and immutable cache selection."""

    cache_dir: Path
    client: FilingClient | None = None

    def refresh(self, start: date, end: date) -> CashMergerSnapshot:
        if end < start:
            raise ValueError("cash-merger event range end precedes start")
        client = self.client or EdgarDailyIndexClient.from_environment()
        events = tuple(
            sorted(
                filter(None, (_event_from_filing(filing) for filing in client.filings(start, end))),
                key=lambda event: (event.available_at, event.target_cik, event.accession),
            )
        )
        snapshot = _snapshot(events, start=start, end=end)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = _snapshot_payload(snapshot)
        identity = str(payload["snapshot_sha256"])
        destination = self.cache_dir / f"cash-merger-events-{identity[:16]}.json"
        _write_once(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return snapshot

    def latest(self) -> CashMergerSnapshot:
        paths = tuple(self.cache_dir.glob("cash-merger-events-*.json"))
        if not paths:
            raise CashMergerSourceError(
                "cash-merger event cache is empty and no live EDGAR snapshot is available"
            )
        snapshots = tuple(load_snapshot(path) for path in paths)
        return max(snapshots, key=lambda item: (item.covered_end, item.retrieved_at))

    def load(self, start: date, end: date, *, refresh: bool = True) -> CashMergerSnapshot:
        """Prefer a live point-in-time tape and fall back to the newest validated cache."""

        if refresh:
            try:
                return self.refresh(start, end)
            except (requests.RequestException, CashMergerSourceError, ValueError) as error:
                warnings.warn(f"EDGAR refresh failed; using cash-merger cache: {error}", stacklevel=2)
        snapshot = self.latest()
        if snapshot.covered_start > start.isoformat() or snapshot.covered_end < end.isoformat():
            raise CashMergerSourceError(
                "newest cash-merger cache does not cover the requested point-in-time range"
            )
        return snapshot


def _event_from_filing(filing: SecFiling) -> CashMergerEvent | None:
    text = re.sub(r"<[^>]+>", " ", filing.text)
    text = re.sub(r"\s+", " ", text)
    if _TERMINATED.search(text):
        status = "terminated"
        offer_price = None
    elif _COMPLETED.search(text):
        status = "completed"
        offer_price = None
    elif _DEFINITIVE.search(text) and _CASH.search(text):
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
    values = [float(match.group(1)) for pattern in _OFFER_PATTERNS for match in pattern.finditer(text)]
    plausible = [value for value in values if 0.01 <= value <= 10_000]
    return max(plausible) if plausible else None


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


def _acceptance_timestamp(text: str, filed_on: str) -> str:
    match = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", text, re.I)
    if match is None:
        return f"{filed_on}T00:00:00+00:00"
    stamp = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return stamp.isoformat()


def _trading_symbol(text: str) -> str | None:
    patterns = (
        r"name=[\"']dei:(?:Entity)?TradingSymbol[\"'][^>]*>\s*(?:<[^>]+>\s*)*([A-Z][A-Z0-9.-]{0,9})",
        r"<dei:(?:Entity)?TradingSymbol[^>]*>\s*([A-Z][A-Z0-9.-]{0,9})\s*</",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match is not None:
            return match.group(1).upper()
    return None


def _index_rows(text: str) -> Iterator[tuple[str, str, str, str, str]]:
    for line in text.splitlines():
        fields = line.split("|")
        if len(fields) != 5 or not fields[0].isdigit():
            continue
        yield fields[0], fields[1], fields[2], fields[3], fields[4]


def _utc_iso(value: str) -> str:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).isoformat()


def _snapshot(
    events: tuple[CashMergerEvent, ...], *, start: date, end: date
) -> CashMergerSnapshot:
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
    if tuple(sorted(events, key=lambda event: (event.available_at, event.target_cik, event.accession))) != events:
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

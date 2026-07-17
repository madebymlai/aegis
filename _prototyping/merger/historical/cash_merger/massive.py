"""Recent fixed-cash merger observations from Massive's documented JSON API."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Protocol

from cash_merger.census import CashMergerEvent, EventStatus

_API_ROOT = "https://api.massive.com"
_DISCLOSURE_PATH = "/stocks/filings/8-K/vX/disclosures"
_INDEX_PATH = "/stocks/filings/vX/index"
_TEXT_PATH = "/stocks/filings/8-K/vX/text"
_AGREEMENT_CATEGORIES = ("merger_agreement", "acquisition_agreement")
_COMPLETION_CATEGORIES = ("merger_completion", "acquisition_completion")
_TERMINATION_CATEGORIES = (
    "deal_termination",
    "deal_withdrawal",
    "deal_breach_default",
)
_OFFER_PATTERNS = (
    re.compile(
        r"(?:agreement|transaction).{0,500}?\$\s*(\d{1,4}(?:\.\d{1,4})?)\s+"
        r"(?:in\s+cash\s+per\s+(?:common\s+)?share|per\s+(?:common\s+)?share(?:\s+in\s+cash)?)",
        re.I | re.S,
    ),
    re.compile(
        r"(?:at|for)\s+(?:a\s+)?(?:purchase\s+)?price\s+of\s+\$\s*"
        r"(\d{1,4}(?:\.\d{1,4})?)\s+per\s+(?:common\s+)?share(?:\s+in\s+cash)?",
        re.I | re.S,
    ),
    re.compile(
        r"(?:each|every).{0,180}?shares?.{0,360}?(?:right\s+to\s+receive|receive)"
        r".{0,120}?\$\s*(\d{1,4}(?:\.\d{1,4})?).{0,80}?"
        r"(?:\bin\s+cash\b|\bper\s+share\b|merger\s+consideration)",
        re.I | re.S,
    ),
    re.compile(
        r"(?:offer|merger)\s+price\s+of\s+\$\s*(\d{1,4}(?:\.\d{1,4})?)"
        r"\s+per\s+(?:common\s+)?share",
        re.I,
    ),
    re.compile(
        r"(?:converted|cancelled|canceled).{0,500}?(?:the\s+)?right\s+to\s+receive\s+"
        r"(?:(?:an\s+amount\s+)?in\s+cash\s+(?:equal\s+to\s+)|"
        r"cash\s+in\s+an\s+amount\s+(?:equal\s+to\s+))\$\s*"
        r"(\d{1,4}(?:\.\d{1,4})?)",
        re.I | re.S,
    ),
    re.compile(
        r"(?:converted|cancelled|canceled).{0,500}?(?:the\s+)?right\s+to\s+receive\s+"
        r"\$\s*"
        r"(\d{1,4}(?:\.\d{1,4})?).{0,100}?(?:\bin\s+cash\b|\bper\s+share\b|"
        r"merger\s+consideration)",
        re.I | re.S,
    ),
)
_NON_CASH = re.compile(
    r"exchange\s+ratio|stock\s+consideration|stock[- ]and[- ]cash|"
    r"contingent\s+value\s+rights?|\bCVRs?\b|earnout",
    re.I,
)
_EQUITY_AWARD = re.compile(
    r"\bRSUs?\b|restricted\s+stock|stock\s+options?|equity\s+awards?|notional\s+units?",
    re.I,
)
_RESOLUTION_LANGUAGE = re.compile(r"merger|acqui(?:sition|red)|transaction", re.I)


class MassiveSourceError(RuntimeError):
    """Massive did not return a complete, interpretable response."""


@dataclass(frozen=True)
class PricePoint:
    trading_date: date
    close: float


class MassiveDataClient(Protocol):
    def disclosures(self, category: str, start: date, end: date) -> Iterable[dict[str, Any]]: ...

    def daily_closes(self, ticker: str, start: date, end: date) -> Iterable[PricePoint]: ...

    def filing_text(self, accession: str, cik: str, filed_on: date) -> str | None: ...


@dataclass
class MassiveClient:
    """Rate-limited Massive client with immutable URL-addressed response reuse."""

    api_key: str
    cache_dir: Path = Path(__file__).resolve().parents[1] / "massive-http"
    minimum_interval_seconds: float = 12.2
    timeout_seconds: int = 90

    def __post_init__(self) -> None:
        self._last_call_at = 0.0

    def disclosures(self, category: str, start: date, end: date) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        url = _DISCLOSURE_PATH
        params: dict[str, object] | None = {
            "tertiary_category": category,
            "filing_date.gte": start.isoformat(),
            "filing_date.lte": end.isoformat(),
            "limit": 1000,
            "sort": "filing_date.asc",
        }
        while url:
            payload = self._get(url, params)
            result = payload.get("results")
            if result is None:
                raise MassiveSourceError(f"Massive omitted results for {category}")
            rows.extend(result)
            next_url = payload.get("next_url")
            url = str(next_url) if next_url else ""
            params = None
        return tuple(rows)

    def filing_index(
        self, form_type: str, start: date, end: date
    ) -> tuple[dict[str, Any], ...]:
        return self._paged(
            _INDEX_PATH,
            {
                "form_type": form_type,
                "filing_date.gte": start.isoformat(),
                "filing_date.lte": end.isoformat(),
                "limit": 10000,
                "sort": "filing_date.asc",
            },
            f"filing index for {form_type}",
        )

    def filing_index_tickers(
        self,
        tickers: Iterable[str],
        form_type: str,
        start: date,
        end: date,
        *,
        batch_size: int = 75,
    ) -> tuple[dict[str, Any], ...]:
        normalized = tuple(sorted({str(ticker).upper() for ticker in tickers}))
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(normalized), batch_size):
            batch = normalized[offset : offset + batch_size]
            rows.extend(
                self._paged(
                    _INDEX_PATH,
                    {
                        "ticker.any_of": ",".join(batch),
                        "form_type": form_type,
                        "filing_date.gte": start.isoformat(),
                        "filing_date.lte": end.isoformat(),
                        "limit": 10000,
                        "sort": "filing_date.asc",
                    },
                    f"{form_type} index for {len(batch)} tickers",
                )
            )
        return tuple(rows)

    def filing_texts(
        self, cik: str, start: date, end: date
    ) -> tuple[dict[str, Any], ...]:
        return self._paged(
            _TEXT_PATH,
            {
                "cik": cik.zfill(10),
                "filing_date.gte": start.isoformat(),
                "filing_date.lte": end.isoformat(),
                "limit": 100,
                "sort": "filing_date.asc",
            },
            f"8-K text for CIK {cik}",
        )

    def filing_texts_many(
        self,
        ciks: Iterable[str],
        start: date,
        end: date,
        *,
        batch_size: int = 75,
    ) -> tuple[dict[str, Any], ...]:
        """Fetch target filing histories in bounded multi-CIK requests."""
        normalized = tuple(sorted({str(cik).lstrip("0").zfill(10) for cik in ciks}))
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(normalized), batch_size):
            batch = normalized[offset : offset + batch_size]
            rows.extend(
                self._paged(
                    _TEXT_PATH,
                    {
                        "cik.any_of": ",".join(batch),
                        "filing_date.gte": start.isoformat(),
                        "filing_date.lte": end.isoformat(),
                        "limit": 99,
                        "sort": "filing_date.asc",
                    },
                    f"8-K text for {len(batch)} target CIKs",
                )
            )
        return tuple(rows)

    def _paged(
        self,
        path: str,
        params: dict[str, object],
        description: str,
    ) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        url = path
        query: dict[str, object] | None = params
        while url:
            payload = self._get(url, query)
            result = payload.get("results")
            if result is None:
                raise MassiveSourceError(f"Massive omitted results for {description}")
            rows.extend(result)
            next_url = payload.get("next_url")
            url = str(next_url) if next_url else ""
            query = None
        return tuple(rows)

    def daily_closes(self, ticker: str, start: date, end: date) -> tuple[PricePoint, ...]:
        encoded = urllib.parse.quote(ticker, safe="")
        payload = self._get(
            f"/v2/aggs/ticker/{encoded}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        return tuple(
            PricePoint(
                trading_date=datetime.fromtimestamp(row["t"] / 1000, UTC).date(),
                close=float(row["c"]),
            )
            for row in payload.get("results") or ()
        )

    def filing_text(self, accession: str, cik: str, filed_on: date) -> str | None:
        payload = self._get(
            _TEXT_PATH,
            {
                "cik": cik.zfill(10),
                "filing_date": filed_on.isoformat(),
                "limit": 100,
                "sort": "filing_date.asc",
            },
        )
        for row in payload.get("results") or ():
            if str(row.get("accession_number") or "") == accession:
                return str(row.get("items_text") or "")
        return None

    def _get(self, path_or_url: str, params: dict[str, object] | None) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("http") else _API_ROOT + path_or_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        cached = self._cached_response(url)
        if cached.exists():
            payload = json.loads(cached.read_text())
        else:
            payload = self._fetch(url)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            _write_once(cached, json.dumps(payload, sort_keys=True, separators=(",", ":")))
        if not isinstance(payload, dict):
            raise MassiveSourceError("Massive response must be a JSON object")
        return payload

    def _fetch(self, url: str) -> dict[str, Any]:
        wait = self.minimum_interval_seconds - (time.monotonic() - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        finally:
            self._last_call_at = time.monotonic()
        return payload

    def _cached_response(self, url: str) -> Path:
        identity = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"massive-{identity}.json"


@dataclass(frozen=True)
class MassiveCashMergerEventSource:
    """Resolve target-side cash deals before emitting lifecycle observations."""

    client: MassiveDataClient

    def events(self, start: date, end: date) -> tuple[CashMergerEvent, ...]:
        agreement_rows = tuple(
            row
            for category in _AGREEMENT_CATEGORIES
            for row in self.client.disclosures(category, start, end)
        )
        pending = self._target_pending_events(agreement_rows)
        known_targets = {_identity(event.target_cik, event.target_symbol) for event in pending}
        completion_rows = tuple(
            row
            for category in _COMPLETION_CATEGORIES
            for row in self.client.disclosures(category, start, end)
        )
        termination_rows = tuple(
            row
            for category in _TERMINATION_CATEGORIES
            for row in self.client.disclosures(category, start, end)
        )
        resolutions = tuple(
            event
            for status, rows in (
                ("completed", completion_rows),
                ("terminated", termination_rows),
            )
            for row in rows
            if (event := _resolution_event(row, status)) is not None
            and _identity(event.target_cik, event.target_symbol) in known_targets
        )
        return tuple(
            sorted(
                {event.accession: event for event in pending + resolutions}.values(),
                key=lambda event: (event.available_at, event.target_cik, event.accession),
            )
        )

    def _target_pending_events(
        self, rows: tuple[dict[str, Any], ...]
    ) -> tuple[CashMergerEvent, ...]:
        accepted_targets: set[str] = set()
        events: list[CashMergerEvent] = []
        ordered = sorted(rows, key=lambda row: (str(row.get("filing_date")), str(row.get("cik"))))
        for row in ordered:
            ticker = _ticker(row)
            supporting_text = str(row.get("supporting_text") or "")
            offer = _offer(supporting_text)
            if ticker is None or offer is None:
                continue
            candidate = _event(row, ticker=ticker, status="pending", offer_price=offer)
            identity = _identity(candidate.target_cik, candidate.target_symbol)
            if identity not in accepted_targets and not self._has_target_price_signature(
                ticker,
                date.fromisoformat(candidate.available_at[:10]),
                offer,
            ):
                continue
            accession = str(row.get("accession_number") or "")
            cik = str(row.get("cik") or "")
            filed_on = date.fromisoformat(str(row["filing_date"]))
            filing_text = self.client.filing_text(accession, cik, filed_on)
            if filing_text is None or _NON_CASH.search(filing_text):
                continue
            accepted_targets.add(identity)
            events.append(candidate)
        return tuple(events)

    def _has_target_price_signature(self, ticker: str, announced: date, offer: float) -> bool:
        prices = tuple(
            self.client.daily_closes(
                ticker,
                announced - timedelta(days=45),
                announced + timedelta(days=10),
            )
        )
        before = [point.close for point in prices if point.trading_date < announced][-20:]
        after = [point.close for point in prices if point.trading_date > announced]
        if len(before) < 10 or not after:
            return False
        unaffected = median(before)
        entry = after[0]
        return 0.0 < unaffected < entry < offer and offer / entry <= 3.0


def _resolution_event(row: dict[str, Any], status: EventStatus) -> CashMergerEvent | None:
    ticker = _ticker(row)
    text = str(row.get("supporting_text") or "")
    if ticker is None or _RESOLUTION_LANGUAGE.search(text) is None:
        return None
    return _event(row, ticker=ticker, status=status, offer_price=None)


def _event(
    row: dict[str, Any],
    *,
    ticker: str,
    status: EventStatus,
    offer_price: float | None,
) -> CashMergerEvent:
    cik = str(row.get("cik") or "").lstrip("0")
    accession = str(row.get("accession_number") or "")
    if not accession:
        accession = f"massive-{cik}-{row['filing_date']}-{status}"
    return CashMergerEvent(
        target_cik=cik or f"ticker:{ticker}",
        target_name=ticker,
        target_symbol=ticker,
        status=status,
        available_at=_available_at(str(row["filing_date"])),
        offer_price=offer_price,
        source_form="8-K",
        source_url=str(
            row.get("filing_url")
            or row.get("source_url")
            or f"https://api.massive.com/stocks/filings/{accession}"
        ),
        accession=accession,
    )


def _ticker(row: dict[str, Any]) -> str | None:
    candidates = [
        str(value).upper()
        for value in row.get("tickers") or ()
        if re.fullmatch(r"[A-Z]{1,5}", str(value).upper())
    ]
    return candidates[0] if candidates else None


def _offer(text: str) -> float | None:
    if not text:
        return None
    values: list[float] = []
    for pattern in _OFFER_PATTERNS:
        for match in pattern.finditer(text):
            price_prefix = text[max(match.start(), match.start(1) - 60) : match.start(1)]
            if re.search(r"par\s+value[^$]{0,30}\$?\s*$", price_prefix, re.I):
                continue
            value = float(match.group(1))
            if 0.25 <= value <= 500.0:
                values.append(value)
    counts = Counter(round(value, 4) for value in values)
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _non_cash_consideration(text: str) -> bool:
    matches = tuple(
        match
        for pattern in _OFFER_PATTERNS
        for match in pattern.finditer(text)
    )
    if not matches:
        return _NON_CASH.search(text) is not None
    for match in matches:
        window = text[max(0, match.start() - 500) : match.end() + 500]
        for non_cash in _NON_CASH.finditer(window):
            context = window[
                max(0, non_cash.start() - 180) : non_cash.end() + 180
            ]
            if non_cash.group(0).casefold() == "exchange ratio" and _EQUITY_AWARD.search(
                context
            ):
                continue
            return True
    return False


def _identity(cik: str, ticker: str) -> str:
    return cik if cik and not cik.startswith("ticker:") else f"ticker:{ticker}"


def _available_at(filing_date: str) -> str:
    """Date-only filings become usable after that session, never during it."""

    observed = datetime.combine(date.fromisoformat(filing_date), datetime.max.time(), UTC)
    return observed.isoformat()


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

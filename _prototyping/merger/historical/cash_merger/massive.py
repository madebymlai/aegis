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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_API_ROOT = "https://api.massive.com"
_DISCLOSURE_PATH = "/stocks/filings/8-K/vX/disclosures"
_TEXT_PATH = "/stocks/filings/8-K/vX/text"
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
class MassiveSourceError(RuntimeError):
    """Massive did not return a complete, interpretable response."""


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

    def aggregate_bars(
        self, ticker: str, start: date, end: date
    ) -> dict[str, Any]:
        """Return one adjusted daily aggregate response through the cache boundary."""

        encoded = urllib.parse.quote(ticker, safe="")
        return self._get(
            f"/v2/aggs/ticker/{encoded}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": 50_000},
        )

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

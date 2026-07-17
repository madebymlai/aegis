"""Prospective three-month Treasury bill rate with immutable raw snapshots."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from .artifacts import write_once

_FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class CashRateUnavailable(RuntimeError):
    """No causal DTB3 observation is available from either FRED or the cache."""


class CashRateTransport(Protocol):
    def fetch(self, start: date, end: date) -> bytes: ...


@dataclass(frozen=True)
class ObservedCashRate:
    """The latest three-month T-bill observation causally available on a date."""

    observed_on: date
    annual_rate: float


class FredCsvTransport:
    """Fetch the public FRED CSV representation without an API key."""

    def fetch(self, start: date, end: date) -> bytes:
        query = urlencode({"id": "DTB3", "cosd": start.isoformat(), "coed": end.isoformat()})
        with urlopen(f"{_FRED_CSV_URL}?{query}", timeout=30) as response:
            return response.read()


class FredDtb3RateSource:
    """Refresh DTB3 dynamically and replay immutable snapshots when FRED is offline."""

    def __init__(self, cache_dir: Path, *, transport: CashRateTransport | None = None) -> None:
        self._cache_dir = cache_dir
        self._transport = transport or FredCsvTransport()

    def latest(self, *, as_of: date) -> ObservedCashRate:
        start = as_of - timedelta(days=30)
        try:
            payload = self._transport.fetch(start, as_of)
            observation = _latest_observation(payload, as_of=as_of)
            identity = hashlib.sha256(payload).hexdigest()
            write_once(self._cache_dir / f"{as_of.isoformat()}-{identity}.csv", payload)
        except (OSError, TimeoutError, CashRateUnavailable):
            cached = self._latest_cached(as_of=as_of)
            if cached is None:
                raise CashRateUnavailable(
                    f"no DTB3 observation is available on or before {as_of.isoformat()}"
                ) from None
            return cached
        else:
            return observation

    def _latest_cached(self, *, as_of: date) -> ObservedCashRate | None:
        available: list[ObservedCashRate] = []
        for path in self._cache_dir.glob("*.csv"):
            try:
                available.append(_latest_observation(path.read_bytes(), as_of=as_of))
            except CashRateUnavailable:
                continue
        return max(available, key=lambda item: item.observed_on) if available else None


def _latest_observation(payload: bytes, *, as_of: date) -> ObservedCashRate:
    try:
        rows = csv.DictReader(StringIO(payload.decode("utf-8-sig")))
        observations = tuple(
            ObservedCashRate(
                date.fromisoformat(row["observation_date"]), float(row["DTB3"]) / 100.0
            )
            for row in rows
            if row.get("DTB3") not in {None, "", "."}
            and date.fromisoformat(row["observation_date"]) <= as_of
        )
    except (KeyError, UnicodeDecodeError, ValueError) as error:
        raise CashRateUnavailable("FRED DTB3 CSV is malformed") from error
    if not observations:
        raise CashRateUnavailable("FRED DTB3 CSV has no causal observation")
    return max(observations, key=lambda item: item.observed_on)

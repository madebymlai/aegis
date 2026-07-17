"""Independent current-deal audit from Ditat's public filing-derived table.

This source is deliberately audit-only. It is not an input to selection, sizing,
or live trading, and it cannot establish historical coverage.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from html import unescape

from cash_merger.census import ReferenceDeal

_URL = "https://www.ditat.io/merger-arb"
_ROW = re.compile(
    r'\{\\"ticker\\":\\"(?P<ticker>.*?)\\",'
    r'\\"target\\":\\"(?P<target>.*?)\\",'
    r'\\"acquirer\\":\\"(?P<acquirer>.*?)\\",'
    r'\\"type\\":\\"(?P<type>.*?)\\"'
    r'.*?\\"sourceUrl\\":\\"(?P<url>.*?)\\"\}',
    re.S,
)


class DitatReferenceError(RuntimeError):
    """The independent current-deal table could not be parsed safely."""


@dataclass(frozen=True)
class DitatPendingCashReferenceSource:
    """Return the current cash-target list as an independent recall denominator."""

    url: str = _URL
    timeout_seconds: int = 30

    def deals(self, start: date, end: date) -> tuple[ReferenceDeal, ...]:
        request = urllib.request.Request(
            self.url,
            headers={"User-Agent": "Aegis personal research coverage audit"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            text = response.read().decode("utf-8")
        rows = tuple(_references(text))
        if not rows:
            raise DitatReferenceError("Ditat returned no parseable pending cash deals")
        return rows


def _references(text: str):
    seen: set[str] = set()
    for match in _ROW.finditer(text):
        if _decode(match.group("type")) != "cash":
            continue
        ticker = _decode(match.group("ticker"))
        if ticker in seen:
            continue
        seen.add(ticker)
        yield ReferenceDeal(
            target_name=_decode(match.group("target")),
            acquirer_name=_decode(match.group("acquirer")),
            source_url=_decode(match.group("url")),
            target_symbol=ticker,
        )


def _decode(value: str) -> str:
    return unescape(json.loads(f'"{value}"'))

"""Independent supported-universe boundary for the merger census audit."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from cash_merger.census import ReferenceDeal, ReferenceSource

_REPORTING_HISTORY = timedelta(days=730)


class FilingEligibilityClient(Protocol):
    def filing_index_tickers(
        self,
        tickers: Iterable[str],
        form_type: str,
        start: date,
        end: date,
    ) -> Iterable[dict[str, Any]]: ...


@dataclass(frozen=True)
class DomesticIssuerReferenceSource:
    """Keep references independently shown to be domestic SEC 10-K filers."""

    references: ReferenceSource
    client: FilingEligibilityClient

    def deals(self, start: date, end: date) -> tuple[ReferenceDeal, ...]:
        candidates = tuple(self.references.deals(start, end))
        symbols = {
            reference.target_symbol
            for reference in candidates
            if reference.target_symbol is not None
        }
        filings = self.client.filing_index_tickers(
            symbols,
            "10-K",
            start - _REPORTING_HISTORY,
            end,
        )
        eligible = {
            str(row.get("ticker") or "").upper()
            for row in filings
            if row.get("ticker")
        }
        return tuple(
            reference
            for reference in candidates
            if reference.target_symbol is not None
            and reference.target_symbol.upper() in eligible
        )

"""Target-safe fixed-cash merger lifecycles from Massive filing data."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from cash_merger.events import CashMergerEvent, EventStatus
from cash_merger.massive import _available_at, _non_cash_consideration, _offer

_AGREEMENTS = ("merger_agreement", "acquisition_agreement")
_COMPLETIONS = ("merger_completion", "acquisition_completion")
_TERMINATIONS = ("deal_termination", "deal_withdrawal", "deal_breach_default")
_SPAC = re.compile(
    r"business\s+combination\s+agreement|de[- ]SPAC|special\s+purpose\s+acquisition",
    re.I,
)
_FILER_IS_COMPANY = re.compile(
    r"(?:^|[.;])[^.;]{0,240}?(?:the\s+)?Company.{0,80}?"
    r"(?:entered\s+into|announced\s+(?:its\s+)?entry\s+into)",
    re.I | re.S,
)
_FIRST_FILER_ROLE = re.compile(
    r"\(\s*(?:the\s+)?['\"](Company|Parent|Buyer)['\"]",
    re.I,
)
_COMPANY_IS_TARGET = re.compile(
    r"(?:merger\s+(?:sub|subsidiary)|parent\s+merger\s+sub).{0,220}?"
    r"(?:will|shall|would)\s+(?:be\s+)?merge(?:d)?\s+with\s+and\s+into\s+"
    r"(?:the\s+)?Company\b"
    r"|(?:the\s+)?Company.{0,220}?surviv(?:e|ing).{0,220}?"
    r"wholly[- ]owned\s+(?:direct\s+)?subsidiary\s+of\s+(?:Parent|Buyer)"
    r"|(?:the\s+)?Company\s+(?:is|will\s+be|would\s+be)\s+"
    r"(?:to\s+be\s+)?acquired"
    r"|(?:the\s+)?Company\s+will\s+(?:be\s+)?merge(?:d)?\s+with\s+and\s+into\s+"
    r"(?:Parent|Buyer)",
    re.I | re.S,
)
_RESOLUTION = re.compile(r"merger|acqui(?:sition|red)|transaction", re.I)


class TargetEventClient(Protocol):
    def disclosures(
        self, category: str, start: date, end: date
    ) -> Iterable[dict[str, Any]]: ...

    def filing_texts_many(
        self, ciks: Iterable[str], start: date, end: date
    ) -> Iterable[dict[str, Any]]: ...

@dataclass(frozen=True)
class MassiveTargetEventSource:
    """Emit only fixed-cash events whose filing text identifies the listed target."""

    client: TargetEventClient

    def events(self, start: date, end: date) -> tuple[CashMergerEvent, ...]:
        return self.load(start, end).events

    def load(self, start: date, end: date) -> "TargetEventTape":
        """Return lifecycle events and the exact causal 8-K rows behind them."""

        agreements = _coalesce_disclosures(
            row
            for category in _AGREEMENTS
            for row in self.client.disclosures(category, start, end)
        )
        unresolved_identity_accessions = tuple(
            sorted(
                str(row.get("accession_number") or "")
                for row in agreements
                if _ticker(row) is None
            )
        )
        explicitly_confirmed = {
            _cik(row) for row in agreements if _cik(row) and _is_target_filer(row)
        }
        provisional_ciks = explicitly_confirmed | {
            _cik(row)
            for row in agreements
            if _cik(row) and _offer(str(row.get("supporting_text") or "")) is not None
        }
        filing_rows = tuple(
            self.client.filing_texts_many(provisional_ciks, start, end)
        )
        texts = {
            str(row.get("accession_number") or ""): str(row.get("items_text") or "")
            for row in filing_rows
        }
        full_text_confirmed = {
            _cik(row)
            for row in agreements
            if (
                full_text := texts.get(str(row.get("accession_number") or ""))
            )
            and _is_target_filer({**row, "supporting_text": full_text})
        }
        target_ciks = explicitly_confirmed | full_text_confirmed
        agreements = tuple(row for row in agreements if _cik(row) in target_ciks)
        pending = tuple(
            event
            for row in agreements
            if (
                event := _pending_event(
                    row,
                    texts,
                    ticker=_ticker(row),
                )
            )
            is not None
        )
        identities = {
            event.target_cik: (event.target_name, event.target_symbol) for event in pending
        }
        resolutions = tuple(
            event
            for status, categories in (
                ("completed", _COMPLETIONS),
                ("terminated", _TERMINATIONS),
            )
            for category in categories
            for row in self.client.disclosures(category, start, end)
            if (event := _resolution_event(row, status, identities)) is not None
        )
        return TargetEventTape(
            events=tuple(sorted(
                {
                    (event.accession, event.status, event.offer_price): event
                    for event in pending + resolutions
                }.values(),
                key=lambda event: (event.available_at, event.target_cik, event.accession),
            )),
            filing_rows=filing_rows,
            unresolved_identity_accessions=unresolved_identity_accessions,
        )


@dataclass(frozen=True)
class TargetEventTape:
    events: tuple[CashMergerEvent, ...]
    filing_rows: tuple[dict[str, Any], ...]
    unresolved_identity_accessions: tuple[str, ...]


def _is_target_filer(row: dict[str, Any]) -> bool:
    text = str(row.get("supporting_text") or "")
    if _SPAC.search(text):
        return False
    first_role = _FIRST_FILER_ROLE.search(text[:500])
    filer_is_company = (
        _FILER_IS_COMPANY.search(text) is not None
        or (first_role is not None and first_role.group(1).casefold() == "company")
    )
    if filer_is_company and _COMPANY_IS_TARGET.search(text):
        return True
    ticker = _ticker(row)
    if ticker is None:
        return False
    escaped = re.escape(ticker)
    ticker_is_target = re.compile(
        rf"(?:merge(?:d)?\s+with\s+and\s+into\s+{escaped}\b.{{0,220}}?"
        rf"{escaped}\b.{{0,100}}?surviv(?:e|ing)|"
        rf"{escaped}\b.{{0,220}}?surviv(?:e|ing).{{0,220}}?"
        rf"wholly[- ]owned\s+subsidiary)",
        re.I | re.S,
    )
    return ticker_is_target.search(text) is not None


def _pending_event(
    row: dict[str, Any],
    texts: dict[str, str],
    *,
    ticker: str | None,
) -> CashMergerEvent | None:
    accession = str(row.get("accession_number") or "")
    text = texts.get(accession)
    if not text or ticker is None or _non_cash_consideration(text):
        return None
    offer = _offer(text)
    if offer is None:
        return None
    return _event(row, ticker, "pending", offer)


def _resolution_event(
    row: dict[str, Any],
    status: EventStatus,
    identities: dict[str, tuple[str, str]],
) -> CashMergerEvent | None:
    identity = identities.get(_cik(row))
    if identity is None or _RESOLUTION.search(str(row.get("supporting_text") or "")) is None:
        return None
    target_name, ticker = identity
    return _event(row, ticker, status, None, target_name=target_name)


def _event(
    row: dict[str, Any],
    ticker: str,
    status: EventStatus,
    offer: float | None,
    *,
    target_name: str | None = None,
) -> CashMergerEvent:
    cik = _cik(row)
    accession = str(row.get("accession_number") or "")
    return CashMergerEvent(
        target_cik=cik,
        target_name=target_name or str(row.get("company_name") or ticker),
        target_symbol=ticker,
        status=status,
        available_at=_available_at(str(row["filing_date"])),
        offer_price=offer,
        source_form="8-K",
        source_url=str(row.get("filing_url") or ""),
        accession=accession or f"massive-{cik}-{row['filing_date']}-{status}",
    )


def _cik(row: dict[str, Any]) -> str:
    return str(row.get("cik") or "").lstrip("0")


def _ticker(row: dict[str, Any]) -> str | None:
    candidates = tuple(
        dict.fromkeys(
            str(value).upper()
            for value in row.get("tickers") or ()
            if re.fullmatch(r"[A-Z]{1,5}", str(value).upper())
        )
    )
    return candidates[0] if len(candidates) == 1 else None


def _coalesce_disclosures(
    rows: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        accession = str(row.get("accession_number") or "")
        grouped.setdefault(accession or repr(sorted(row.items())), []).append(row)
    merged: list[dict[str, Any]] = []
    for duplicates in grouped.values():
        base = max(
            duplicates,
            key=lambda row: len(str(row.get("supporting_text") or "")),
        )
        texts = tuple(
            dict.fromkeys(
                str(row.get("supporting_text") or "")
                for row in duplicates
                if row.get("supporting_text")
            )
        )
        tickers = next(
            (row.get("tickers") for row in duplicates if row.get("tickers")),
            (),
        )
        merged.append(
            {
                **base,
                "tickers": tickers,
                "supporting_text": "\n".join(texts),
            }
        )
    return tuple(merged)

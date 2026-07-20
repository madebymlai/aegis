"""Event-derived adapters for the recent Massive cash-merger replay."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from _prototyping.merger.shadow.edgar import (
    SourceRefresh,
    SourceReview,
    _timeline_evidence,
)
from _prototyping.merger.shadow.ledger import EventObservation, EventStatus
from _prototyping.merger.shadow.market import (
    MarketMarkBatch,
    MarketUnavailable,
    _mark,
)
from cash_merger.events import CashMergerEvent


class CachedEvidenceError(RuntimeError):
    """A retained Massive response cannot be interpreted causally."""


class HistoricalBars(Protocol):
    """Daily market history addressed by the event-time ticker."""

    def bars(self, ticker: str, start: date, end: date) -> pd.DataFrame: ...


class MassiveAggregateClient(Protocol):
    cache_dir: Path

    def aggregate_bars(
        self, ticker: str, start: date, end: date
    ) -> dict[str, Any]: ...


class MassiveOfflineEvidenceClient:
    """Query immutable Massive response rows without deriving a cached cohort.

    The cache is a bag of source observations.  Every query is evaluated from
    the observations' own causal fields; file presence and prior request shape
    never determine which issuers belong to the historical universe.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._rows = self._load_rows(cache_dir)

    @property
    def event_disclosure_date_bounds(self) -> tuple[date, date] | None:
        """Return observed deal-disclosure bounds without claiming completeness."""

        filing_dates = tuple(
            observed
            for row in self._rows
            if row.get("tertiary_category") is not None
            and (observed := _filing_date(row)) is not None
        )
        if not filing_dates:
            return None
        return min(filing_dates), max(filing_dates)

    def disclosures(
        self, category: str, start: date, end: date
    ) -> tuple[dict[str, Any], ...]:
        return self._matching(
            start,
            end,
            lambda row: row.get("tertiary_category") == category,
        )

    def filing_texts_many(
        self,
        ciks: Iterable[str],
        start: date,
        end: date,
        *,
        batch_size: int = 75,
    ) -> tuple[dict[str, Any], ...]:
        del batch_size
        accepted = {_normalize_cik(cik) for cik in ciks}
        return self._matching(
            start,
            end,
            lambda row: "items_text" in row
            and _normalize_cik(row.get("cik")) in accepted,
        )

    def filing_index(
        self, form_type: str, start: date, end: date
    ) -> tuple[dict[str, Any], ...]:
        return self._matching(
            start,
            end,
            lambda row: row.get("form_type") == form_type
            and "items_text" not in row,
        )

    def _matching(
        self,
        start: date,
        end: date,
        predicate,
    ) -> tuple[dict[str, Any], ...]:
        if end < start:
            raise ValueError("evidence query end precedes start")
        rows = (
            row
            for row in self._rows
            if predicate(row) and _row_in_range(row, start, end)
        )
        return tuple(
            sorted(
                _deduplicate(rows),
                key=lambda row: (
                    str(row.get("filing_date") or ""),
                    str(row.get("cik") or ""),
                    str(row.get("accession_number") or ""),
                ),
            )
        )

    @staticmethod
    def _load_rows(cache_dir: Path) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        if not cache_dir.is_dir():
            return ()
        for path in cache_dir.glob("massive-*.json"):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as error:
                raise CachedEvidenceError(f"cannot read cached response {path}") from error
            result = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(result, list):
                continue
            rows.extend(row for row in result if isinstance(row, dict))
        return tuple(rows)


def _normalize_cik(value: object) -> str:
    return str(value or "").lstrip("0")


def _row_in_range(row: dict[str, Any], start: date, end: date) -> bool:
    observed = _filing_date(row)
    return observed is not None and start <= observed <= end


def _filing_date(row: dict[str, Any]) -> date | None:
    if "filing_date" not in row:
        return None
    try:
        return date.fromisoformat(str(row["filing_date"]))
    except (TypeError, ValueError) as error:
        raise CachedEvidenceError("cached filing has an invalid filing_date") from error


def _deduplicate(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = json.dumps(row, sort_keys=True, separators=(",", ":"))
        unique.setdefault(identity, row)
    return tuple(unique.values())


class MassiveHistoricalBars:
    """Serve complete OHLCV windows from cached or freshly requested aggregates."""

    def __init__(
        self,
        client: MassiveAggregateClient,
        *,
        allow_fetch: bool = True,
    ) -> None:
        self._client = client
        self._allow_fetch = allow_fetch
        self._rows = self._index_cache(client.cache_dir)

    def bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        normalized = ticker.upper()
        cached = self._rows.get(normalized, {})
        covers = (
            bool(cached)
            and min(cached) <= start + timedelta(days=7)
            and max(cached) >= end - timedelta(days=7)
        )
        if not covers and self._allow_fetch:
            payload = self._client.aggregate_bars(normalized, start, end)
            self._ingest(payload)
            cached = self._rows.get(normalized, {})
        rows = [row for day, row in sorted(cached.items()) if start <= day <= end]
        if not rows:
            return pd.DataFrame(
                columns=["Open", "High", "Low", "Close", "Volume"],
                index=pd.DatetimeIndex([]),
            )
        return pd.DataFrame(
            {
                "Open": [float(row["o"]) for row in rows],
                "High": [float(row["h"]) for row in rows],
                "Low": [float(row["l"]) for row in rows],
                "Close": [float(row["c"]) for row in rows],
                "Volume": [float(row.get("v") or 0.0) for row in rows],
            },
            index=pd.DatetimeIndex([pd.Timestamp(row["date"]) for row in rows]),
        )

    def _ingest(self, payload: dict[str, Any]) -> None:
        ticker = str(payload.get("ticker") or "").upper()
        if not ticker:
            return
        for row in payload.get("results") or ():
            if not isinstance(row, dict) or not {"t", "o", "h", "l", "c"} <= row.keys():
                continue
            day = datetime.fromtimestamp(float(row["t"]) / 1_000.0, UTC).date()
            self._rows.setdefault(ticker, {})[day] = {**row, "date": day.isoformat()}

    @classmethod
    def _index_cache(cls, cache_dir: Path) -> dict[str, dict[date, dict[str, Any]]]:
        rows: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
        if not cache_dir.is_dir():
            return {}
        instance = object.__new__(cls)
        instance._rows = rows
        for path in cache_dir.glob("massive-*.json"):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as error:
                raise CachedEvidenceError(f"cannot read cached response {path}") from error
            if isinstance(payload, dict):
                instance._ingest(payload)
        return dict(rows)


@dataclass(frozen=True)
class _ActiveLifecycle:
    event_id: str
    instrument_id: str
    agreement_accession: str
    agreement_date: str


def adapt_events(
    events: Iterable[CashMergerEvent],
    *,
    filing_rows: Iterable[dict[str, Any]] = (),
) -> tuple[tuple[EventObservation, ...], tuple[SourceReview, ...]]:
    """Convert the market-wide event tape without consulting a configured universe."""

    filing_text = {
        str(row.get("accession_number") or ""): str(row.get("items_text") or "")
        for row in filing_rows
    }
    active: dict[str, _ActiveLifecycle] = {}
    observations: list[EventObservation] = []
    reviews: list[SourceReview] = []
    ordered = sorted(
        events,
        key=lambda item: (
            item.available_at,
            item.target_cik,
            0 if item.status != "pending" else 1,
            item.accession,
        ),
    )
    for event in ordered:
        lifecycle = active.get(event.target_cik)
        if event.status == "pending":
            if lifecycle is None:
                lifecycle = _ActiveLifecycle(
                    event_id=f"{event.target_cik}:{event.accession}",
                    instrument_id=_historical_instrument_id(event),
                    agreement_accession=event.accession,
                    agreement_date=event.available_at[:10],
                )
                active[event.target_cik] = lifecycle
                status = EventStatus.ANNOUNCED
            else:
                status = EventStatus.AMENDED
        else:
            if lifecycle is None:
                reviews.append(
                    SourceReview(
                        accession=event.accession,
                        cik=event.target_cik,
                        ticker=event.target_symbol,
                        reason="terminal event has no causally active fixed-cash agreement",
                    )
                )
                continue
            status = (
                EventStatus.COMPLETED
                if event.status == "completed"
                else EventStatus.TERMINATED
            )

        observations.append(
            EventObservation(
                event_id=lifecycle.event_id,
                instrument_id=lifecycle.instrument_id,
                target_cik=event.target_cik,
                ticker=event.target_symbol,
                agreement_accession=lifecycle.agreement_accession,
                agreement_date=lifecycle.agreement_date,
                observed_at=event.available_at,
                status=status,
                offer_price=event.offer_price,
                source_accession=event.accession,
                source_url=event.source_url,
                evidence=f"Massive event tape {event.source_form} {event.status}",
                timeline=_timeline_evidence(filing_text.get(event.accession, "")),
            )
        )
        if event.status != "pending":
            active.pop(event.target_cik, None)

    return (
        tuple(observations),
        tuple(sorted(reviews, key=lambda item: (item.accession, item.reason))),
    )


def _historical_instrument_id(event: CashMergerEvent) -> str:
    """Preserve the event-time ticker and issuer CIK without current-symbol lookup."""

    return f"{event.target_symbol}@CIK{event.target_cik}"


@dataclass(frozen=True)
class MassiveEventTapeSource:
    """Replay an immutable market-wide event tape through the shadow source port."""

    observations: tuple[EventObservation, ...]
    reviews: tuple[SourceReview, ...] = ()

    def refresh(
        self,
        *,
        start: date,
        end: date,
        active_events: Iterable[EventObservation],
    ) -> SourceRefresh:
        del active_events
        if end < start:
            raise ValueError("Massive event-tape refresh end precedes start")
        return SourceRefresh(
            observations=tuple(
                item
                for item in self.observations
                if start <= date.fromisoformat(item.observed_at[:10]) <= end
            ),
            reviews=tuple(
                review
                for review in self.reviews
                if any(
                    item.source_accession == review.accession
                    and start <= date.fromisoformat(item.observed_at[:10]) <= end
                    for item in self.observations
                )
            ),
        )


class MassiveMarkSource:
    """Build the active selector's market marks from Massive daily history."""

    def __init__(
        self,
        bars: HistoricalBars,
        *,
        annual_cash_rate: float,
        market_ticker: str = "SPY",
    ) -> None:
        self._bars = bars
        self._annual_cash_rate = annual_cash_rate
        self._market_ticker = market_ticker

    def load(
        self,
        events: Iterable[EventObservation],
        *,
        as_of: datetime,
    ) -> MarketMarkBatch:
        pending = tuple(
            event
            for event in events
            if event.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}
        )
        if not pending:
            return MarketMarkBatch((), ())
        earliest = min(datetime.fromisoformat(event.observed_at) for event in pending)
        start = (earliest - timedelta(days=100)).date()
        end = as_of.date()
        market = self._bars.bars(self._market_ticker, start, end)
        marks = []
        unavailable = []
        for event in sorted(pending, key=lambda item: item.event_id):
            target = self._bars.bars(event.ticker, start, end)
            mark, reason = _mark(
                event,
                target,
                market,
                as_of=as_of,
                annual_cash_rate=self._annual_cash_rate,
            )
            if mark is not None:
                marks.append(mark)
            if reason is not None:
                unavailable.append(MarketUnavailable(event.event_id, event.ticker, reason))
        return MarketMarkBatch(tuple(marks), tuple(unavailable))

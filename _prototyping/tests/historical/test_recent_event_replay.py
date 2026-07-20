from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from _prototyping.merger.historical.recent import (
    MassiveEventTapeSource,
    MassiveHistoricalBars,
    MassiveMarkSource,
    MassiveOfflineEvidenceClient,
    adapt_events,
)
from _prototyping.merger.shadow.ledger import EventStatus
from _prototyping.merger.run_recent_event_history import (
    HistoricalReplayInputError,
    run_recent_event_history,
)
from cash_merger.events import CashMergerEvent
from cash_merger.target_events import MassiveTargetEventSource


def _event(
    cik: str,
    symbol: str,
    accession: str,
    available_at: str,
    status: str,
    offer: float | None,
) -> CashMergerEvent:
    return CashMergerEvent(
        target_cik=cik,
        target_name=f"Target {cik}",
        target_symbol=symbol,
        status=status,
        available_at=available_at,
        offer_price=offer,
        source_form="8-K",
        source_url=f"https://example.test/{accession}",
        accession=accession,
    )


def test_event_tape_generates_membership_from_each_announced_lifecycle() -> None:
    observations, reviews = adapt_events(
        (
            _event("1001", "OLD", "one", "2024-08-01T23:59:59+00:00", "pending", 10.0),
            _event("1001", "OLD", "two", "2024-08-15T23:59:59+00:00", "pending", 11.0),
            _event("1001", "OLD", "three", "2024-09-01T23:59:59+00:00", "completed", None),
            _event("2002", "NEW", "four", "2025-01-02T23:59:59+00:00", "pending", 20.0),
        )
    )

    assert reviews == ()
    assert [(item.event_id, item.instrument_id, item.status) for item in observations] == [
        ("1001:one", "OLD@CIK1001", EventStatus.ANNOUNCED),
        ("1001:one", "OLD@CIK1001", EventStatus.AMENDED),
        ("1001:one", "OLD@CIK1001", EventStatus.COMPLETED),
        ("2002:four", "NEW@CIK2002", EventStatus.ANNOUNCED),
    ]


def test_event_tape_reuses_active_timeline_parser_for_the_agreement_text() -> None:
    observations, reviews = adapt_events(
        (
            _event("1001", "OLD", "one", "2024-08-01T23:59:59+00:00", "pending", 10.0),
        ),
        filing_rows=(
            {
                "accession_number": "one",
                "items_text": "The transaction is expected to close in the fourth quarter of 2024.",
            },
        ),
    )

    assert reviews == ()
    assert observations[0].timeline is not None
    assert observations[0].timeline.guidance is not None
    assert observations[0].timeline.guidance.earliest == "2024-10-01"
    assert observations[0].timeline.guidance.latest == "2024-12-31"


def test_event_source_filters_the_dynamic_tape_by_causal_refresh_window() -> None:
    observations, _reviews = adapt_events(
        (
            _event("1001", "OLD", "one", "2024-08-01T23:59:59+00:00", "pending", 10.0),
            _event("2002", "NEW", "two", "2025-01-02T23:59:59+00:00", "pending", 20.0),
        )
    )
    source = MassiveEventTapeSource(observations)

    refresh = source.refresh(
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
        active_events=(),
    )

    assert [item.ticker for item in refresh.observations] == ["NEW"]


class _Bars:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        self.requested.append(ticker)
        index = pd.bdate_range("2024-06-03", "2024-08-30")
        offset = 0.2 if ticker == "SPY" else 0.1
        close = 50.0 + np.arange(len(index), dtype=float) * offset
        return pd.DataFrame(
            {
                "Open": close,
                "High": close,
                "Low": close,
                "Close": close,
                "Volume": np.full(len(index), 1_000_000.0),
            },
            index=index,
        )


def test_massive_marks_request_only_the_market_and_currently_active_targets() -> None:
    events, _reviews = adapt_events(
        (
            _event("1001", "OLD", "one", "2024-08-01T23:59:59+00:00", "pending", 60.0),
            _event("2002", "DONE", "two", "2024-07-01T23:59:59+00:00", "pending", 60.0),
            _event("2002", "DONE", "three", "2024-07-15T23:59:59+00:00", "completed", None),
        )
    )
    bars = _Bars()
    old_active = next(item for item in events if item.ticker == "OLD")
    done_terminal = next(
        item for item in events if item.ticker == "DONE" and item.status is EventStatus.COMPLETED
    )

    batch = MassiveMarkSource(bars, annual_cash_rate=0.04).load(
        (old_active, done_terminal),
        as_of=datetime(2024, 8, 30, 23, 59, tzinfo=UTC),
    )

    assert bars.requested == ["SPY", "OLD"]
    assert [mark.instrument_id for mark in batch.marks] == ["OLD@CIK1001"]
    assert batch.unavailable == ()


class _AggregateClient:
    cache_dir = None

    def __init__(self) -> None:
        self.request = None

    def aggregate_bars(self, ticker, start, end):
        self.request = (ticker, start, end)
        return {
            "ticker": "OLD",
            "results": [
                {
                    "t": int(datetime(2024, 7, 22, tzinfo=UTC).timestamp() * 1_000),
                    "o": 40.0,
                    "h": 43.0,
                    "l": 39.5,
                    "c": 42.5,
                    "v": 1_500_000,
                }
            ],
        }


def test_historical_bars_loads_adjusted_ohlcv_from_one_massive_window(tmp_path) -> None:
    client = _AggregateClient()
    client.cache_dir = tmp_path
    source = MassiveHistoricalBars(client)

    frame = source.bars("OLD", date(2024, 7, 20), date(2024, 7, 23))

    assert client.request == ("OLD", date(2024, 7, 20), date(2024, 7, 23))
    assert frame.loc[pd.Timestamp("2024-07-22")].to_dict() == {
        "Open": 40.0,
        "High": 43.0,
        "Low": 39.5,
        "Close": 42.5,
        "Volume": 1_500_000.0,
    }


def test_historical_bars_can_audit_an_incomplete_cache_without_network(tmp_path) -> None:
    client = _AggregateClient()
    client.cache_dir = tmp_path
    _cache_payload(
        tmp_path,
        "massive-bar.json",
        [
            {
                "t": int(datetime(2024, 7, 22, tzinfo=UTC).timestamp() * 1_000),
                "o": 40.0,
                "h": 43.0,
                "l": 39.5,
                "c": 42.5,
                "v": 1_500_000,
            }
        ],
    )
    payload = __import__("json").loads((tmp_path / "massive-bar.json").read_text())
    payload["ticker"] = "OLD"
    (tmp_path / "massive-bar.json").write_text(__import__("json").dumps(payload))
    source = MassiveHistoricalBars(client, allow_fetch=False)

    frame = source.bars("OLD", date(2024, 1, 1), date(2024, 12, 31))

    assert client.request is None
    assert list(frame.index) == [pd.Timestamp("2024-07-22")]


def _cache_payload(tmp_path, name: str, rows: list[dict]) -> None:
    (tmp_path / name).write_text(__import__("json").dumps({"results": rows}))


def test_offline_evidence_filters_cached_rows_by_causal_fields_and_deduplicates(
    tmp_path,
) -> None:
    disclosure = {
        "accession_number": "agreement-1",
        "cik": "0000001001",
        "filing_date": "2024-08-01",
        "filing_url": "https://example.test/agreement-1",
        "primary_category": "strategic_transactions",
        "secondary_category": "deal_agreements",
        "tertiary_category": "merger_agreement",
        "supporting_text": "Company agreed to be acquired for $10.00 per share in cash.",
        "tickers": ["OLD"],
    }
    _cache_payload(tmp_path, "massive-one.json", [disclosure])
    _cache_payload(tmp_path, "massive-duplicate.json", [disclosure])
    _cache_payload(
        tmp_path,
        "massive-other.json",
        [
            {**disclosure, "accession_number": "outside", "filing_date": "2023-01-01"},
            {**disclosure, "accession_number": "wrong-kind", "tertiary_category": "deal_termination"},
        ],
    )
    client = MassiveOfflineEvidenceClient(tmp_path)

    rows = client.disclosures("merger_agreement", date(2024, 1, 1), date(2024, 12, 31))

    assert rows == (disclosure,)


def test_offline_evidence_filters_filing_text_and_index_rows(tmp_path) -> None:
    text = {
        "accession_number": "agreement-1",
        "cik": "0000001001",
        "filing_date": "2024-08-01",
        "filing_url": "https://example.test/agreement-1",
        "form_type": "8-K",
        "items_text": "Agreement text",
        "ticker": "OLD",
    }
    index = {
        "accession_number": "proxy-1",
        "cik": "0000001001",
        "filing_date": "2024-08-20",
        "filing_url": "https://example.test/proxy-1",
        "form_type": "DEFM14A",
        "issuer_name": "Old Target",
        "ticker": "OLD",
    }
    _cache_payload(tmp_path, "massive-text.json", [text])
    _cache_payload(tmp_path, "massive-index.json", [index])
    client = MassiveOfflineEvidenceClient(tmp_path)

    assert client.filing_texts_many(
        ["1001"], date(2024, 1, 1), date(2024, 12, 31)
    ) == (text,)
    assert client.filing_index(
        "DEFM14A", date(2024, 1, 1), date(2024, 12, 31)
    ) == (index,)


def test_recent_history_seeds_pre_window_announcements_into_the_active_ledger(
    tmp_path,
) -> None:
    _cache_payload(
        tmp_path,
        "massive-agreement.json",
        [
            {
                "accession_number": "warmup-agreement",
                "cik": "0000004001",
                "company_name": "Example Target Inc.",
                "filing_date": "2023-06-01",
                "filing_url": "https://example.test/warmup-agreement",
                "primary_category": "strategic_transactions",
                "secondary_category": "deal_agreements",
                "tertiary_category": "merger_agreement",
                "supporting_text": (
                    "The Company entered into a merger agreement with Parent and Merger "
                    "Sub. Merger Sub will merge with and into the Company, with the "
                    "Company surviving as a wholly-owned subsidiary of Parent."
                ),
                "tickers": ["TGT"],
            }
        ],
    )
    _cache_payload(
        tmp_path,
        "massive-text.json",
        [
            {
                "accession_number": "warmup-agreement",
                "cik": "0000004001",
                "filing_date": "2023-06-01",
                "filing_url": "https://example.test/warmup-agreement",
                "form_type": "8-K",
                "items_text": (
                    "Each share will receive $100.00 per share in cash under the merger. "
                    "The transaction is expected to close in the fourth quarter of 2024."
                ),
                "ticker": "TGT",
            }
        ],
    )
    _cache_payload(
        tmp_path,
        "massive-unrelated-index.json",
        [
            {
                "accession_number": "old-10k",
                "cik": "0000009999",
                "filing_date": "1999-01-01",
                "filing_url": "https://example.test/old-10k",
                "form_type": "10-K",
                "issuer_name": "Unrelated Issuer",
                "ticker": "OTHER",
            }
        ],
    )
    market_payload = {
        "ticker": "SPY",
        "results": [
            {
                "t": int(datetime(2024, 7, 16, tzinfo=UTC).timestamp() * 1_000),
                "o": 550.0,
                "h": 551.0,
                "l": 549.0,
                "c": 550.5,
                "v": 10_000_000,
            }
        ],
    }
    (tmp_path / "massive-market.json").write_text(
        __import__("json").dumps(market_payload)
    )

    report = run_recent_event_history(
        cache_dir=tmp_path,
        event_start=date(1990, 1, 1),
        start=date(2024, 7, 16),
        end=date(2024, 7, 16),
        capital=100_000.0,
        annual_cash_rate=0.04,
    )

    assert report["window"]["event_discovery_start"] == "1990-01-01"
    assert report["window"]["source_evidence_start"] == "2023-06-01"
    assert report["window"]["warmup_coverage_satisfied"] is False
    assert report["event_tape"]["lifecycles"] == 1
    assert report["selection_audit"]["selection_exclusions"] == {
        "missing_offer_or_mark": 1
    }


class _FutureProxyOnlyTarget:
    def disclosures(self, category: str, start: date, end: date):
        del start, end
        if category != "merger_agreement":
            return ()
        return (
            {
                "accession_number": "ambiguous-announcement",
                "cik": "0000004002",
                "filing_date": "2024-01-02",
                "supporting_text": "Each share will receive $20.00 per share in cash.",
                "tickers": ["OLD", "NEW"],
            },
        )

    def filing_texts_many(self, ciks, start: date, end: date):
        del ciks, start, end
        return (
            {
                "accession_number": "ambiguous-announcement",
                "cik": "0000004002",
                "filing_date": "2024-01-02",
                "items_text": "Each share will receive $20.00 per share in cash.",
            },
        )

    def filing_index(self, form_type: str, start: date, end: date):
        del start, end
        if form_type != "DEFM14A":
            return ()
        return (
            {
                "accession_number": "future-proxy",
                "cik": "0000004002",
                "filing_date": "2024-02-01",
                "form_type": "DEFM14A",
                "ticker": "NEW",
            },
        )


def test_future_proxy_cannot_supply_an_announcement_time_target_identity() -> None:
    source = MassiveTargetEventSource(_FutureProxyOnlyTarget())

    tape = source.load(date(2024, 1, 1), date(2024, 12, 31))

    assert tape.events == ()
    assert tape.unresolved_identity_accessions == ("ambiguous-announcement",)


def test_recent_history_rejects_a_discovery_start_after_1990(tmp_path) -> None:
    with pytest.raises(
        HistoricalReplayInputError,
        match="event discovery must begin by 1990-01-01",
    ):
        run_recent_event_history(
            cache_dir=tmp_path,
            event_start=date(1991, 1, 1),
            start=date(2024, 7, 16),
            end=date(2024, 7, 16),
            capital=100_000.0,
            annual_cash_rate=0.04,
        )

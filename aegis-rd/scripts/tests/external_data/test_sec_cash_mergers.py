from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
import requests

from research.aegis_research.external_data.ecb_fx import EcbUsdEurSource
from research.aegis_research.external_data.sec_cash_mergers import (
    CashMergerSourceError,
    EdgarMasterIndexClient,
    SecCashMergerEventSource,
    SecFiling,
)


class _Filings:
    def filings(self, start: date, end: date):
        common = {
            "cik": "1001",
            "company_name": "Example Target Inc.",
            "symbol": "TGTX",
            "form": "8-K",
        }
        return [
            SecFiling(
                **common,
                accession="0001",
                filed_at="2026-01-05T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0001.txt",
                text=(
                    "The company entered into an Agreement and Plan of Merger. "
                    "Holders will receive $100.00 in cash per share."
                ),
            ),
            SecFiling(
                **common,
                accession="0002",
                filed_at="2026-01-10T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0002.txt",
                text=(
                    "The definitive merger agreement was amended. The revised cash "
                    "consideration is $110.00 in cash per share."
                ),
            ),
            SecFiling(
                **common,
                accession="0003",
                filed_at="2026-01-13T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0003.txt",
                text="The parties terminated the merger agreement.",
            ),
        ]


class _UnavailableFilings:
    def filings(self, start: date, end: date):
        raise requests.ConnectionError("offline")


class _NoFilings:
    def filings(self, start: date, end: date):
        return []


class _NoisyProxyFiling:
    def filings(self, start: date, end: date):
        return [
            SecFiling(
                cik="1001",
                company_name="Example Target Inc.",
                symbol="TGTX",
                form="DEFM14A",
                accession="0004",
                filed_at="2026-01-05T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0004.txt",
                text=(
                    "<DOCUMENT><TYPE>DEFM14A<TEXT>"
                    "The company entered into an Agreement and Plan of Merger to acquire "
                    "all common stock, par value $0.0001 per share, at a price of $48.00 "
                    "per share in cash. Earlier proposals were $32.00 per share in cash "
                    "and analyst targets reached $70.00 per share. The agreement may be "
                    "terminated under specified conditions."
                    "</TEXT></DOCUMENT>"
                    "<DOCUMENT><TYPE>EX-2.1<TEXT>Termination of the merger agreement."
                    "</TEXT></DOCUMENT>"
                ),
            )
        ]


class _StockAndCashFiling:
    def filings(self, start: date, end: date):
        return [
            SecFiling(
                cik="1002",
                company_name="Stock And Cash Target Inc.",
                symbol="MIXED",
                form="DEFM14A",
                accession="0005",
                filed_at="2026-01-06T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1002/0005.txt",
                text=(
                    "The companies entered into an Agreement and Plan of Merger. "
                    "Each target share will receive one share of buyer common stock "
                    "and $88.82 in cash per share."
                ),
            )
        ]


class _TenderWithCvrFiling:
    def filings(self, start: date, end: date):
        return [
            SecFiling(
                cik="1004",
                company_name="Tender Target Inc.",
                symbol="CVRT",
                form="SC 14D9",
                accession="0007",
                filed_at="2026-01-08T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1004/0007.txt",
                text=(
                    "The company entered into a definitive merger agreement. "
                    "Holders will receive $20.00 in cash per share and one contingent "
                    "value right payable after regulatory approval."
                ),
            )
        ]


class _PendingEightKFiling:
    def filings(self, start: date, end: date):
        return [
            SecFiling(
                cik="1003",
                company_name="Pending Target Inc.",
                symbol="PEND",
                form="8-K",
                accession="0006",
                filed_at="2026-01-07T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1003/0006.txt",
                text=(
                    "The company entered into an Agreement and Plan of Merger at a "
                    "price of $25.00 per share in cash. The termination of the merger "
                    "agreement remains possible under specified conditions."
                ),
            )
        ]


class _MissingPrimaryDocumentFiling:
    def filings(self, start: date, end: date):
        return [
            SecFiling(
                cik="1005",
                company_name="Missing Primary Target Inc.",
                symbol="MISS",
                form="DEFM14A",
                accession="0008",
                filed_at="2026-01-09T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1005/0008.txt",
                text=(
                    "<DOCUMENT><TYPE>EX-2.1<TEXT>"
                    "The company entered into an Agreement and Plan of Merger. "
                    "Holders will receive $100.00 in cash per share."
                    "</TEXT></DOCUMENT>"
                ),
            )
        ]


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class _EdgarSession:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, url: str, *, timeout: int) -> _Response:
        if url in self.pages:
            return _Response(self.pages[url])
        if "/full-index/" in url:
            return _Response("", status_code=404)
        raise AssertionError(f"unexpected fake EDGAR request: {url}")


class _Fx:
    def usd_per_eur(self, start: date, end: date) -> pd.Series:
        return pd.Series(
            [1.25, 1.20],
            index=pd.to_datetime([start.isoformat(), end.isoformat()]),
        )


def test_edgar_client_uses_the_repository_contact_identity(monkeypatch) -> None:
    session = _EdgarSession({})
    monkeypatch.setattr(requests, "Session", lambda: session)

    tuple(
        EdgarMasterIndexClient(minimum_request_interval_seconds=0.0).filings(
            date(2026, 1, 1), date(2026, 1, 15)
        )
    )

    assert session.headers["User-Agent"] == "Aegis Research m@laimk.dev"


def test_event_source_preserves_each_causal_filing_and_reads_validated_offline_cache(
    tmp_path,
) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_Filings())

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    live = SecCashMergerEventSource(tmp_path / "events").load_cached(
        date(2026, 1, 1), date(2026, 1, 15)
    )
    cached = SecCashMergerEventSource(tmp_path / "events").load_cached(
        date(2026, 1, 1), date(2026, 1, 15)
    )

    assert len(live.events) == 3
    assert (live.events[0].status, live.events[0].offer_price) == ("pending", 100.0)
    assert (live.events[1].status, live.events[1].offer_price) == ("pending", 110.0)
    assert (live.events[2].status, live.events[2].offer_price) == ("terminated", None)
    assert cached.events == live.events
    assert live.events[0].available_at == "2026-01-05T16:00:00+00:00"
    assert live.events[0].source_url.endswith("/0001.txt")
    assert live.source_sha256


def test_event_source_fails_clearly_without_live_data_or_cache(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "empty")

    with pytest.raises(CashMergerSourceError, match="cache is empty"):
        source.load_cached(date(2026, 1, 1), date(2026, 1, 15))


def test_event_source_rejects_an_empty_refresh_without_caching_it(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_NoFilings())

    with pytest.raises(CashMergerSourceError, match="no fixed-cash merger events"):
        source.refresh(date(2026, 1, 1), date(2026, 1, 15))

    assert not tuple((tmp_path / "events").glob("cash-merger-events-*.json"))


def test_event_source_reads_the_primary_transaction_terms_not_boilerplate_or_history(
    tmp_path,
) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_NoisyProxyFiling())

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    snapshot = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert len(snapshot.events) == 1
    assert (snapshot.events[0].status, snapshot.events[0].offer_price) == ("pending", 48.0)


def test_event_source_excludes_stock_and_cash_consideration(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_StockAndCashFiling())

    with pytest.raises(CashMergerSourceError, match="no fixed-cash merger events"):
        source.refresh(date(2026, 1, 1), date(2026, 1, 15))


def test_event_source_excludes_tender_offers_with_contingent_value_rights(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_TenderWithCvrFiling())

    with pytest.raises(CashMergerSourceError, match="no fixed-cash merger events"):
        source.refresh(date(2026, 1, 1), date(2026, 1, 15))


def test_event_source_does_not_treat_a_termination_clause_as_a_termination(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_PendingEightKFiling())

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    snapshot = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert len(snapshot.events) == 1
    assert (snapshot.events[0].status, snapshot.events[0].offer_price) == ("pending", 25.0)


def test_event_source_rejects_submission_without_the_filing_primary_document(
    tmp_path,
) -> None:
    source = SecCashMergerEventSource(
        tmp_path / "events", client=_MissingPrimaryDocumentFiling()
    )

    with pytest.raises(CashMergerSourceError, match="no fixed-cash merger events"):
        source.refresh(date(2026, 1, 1), date(2026, 1, 15))


def test_edgar_source_resolves_the_announcement_ticker_from_a_preceding_cover_filing(
    tmp_path, monkeypatch
) -> None:
    index = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
    archive = "https://www.sec.gov/Archives/{path}"
    cover_path = "edgar/data/1001/0001.txt"
    proxy_path = "edgar/data/1001/0002.txt"
    resolution_path = "edgar/data/1001/0003.txt"
    later_cover_path = "edgar/data/1001/0004.txt"
    pages = {
        index.format(year=2025, quarter=4): (
            f"1001|Example Target Inc.|10-Q|2025-11-01|{cover_path}\n"
        ),
        index.format(year=2026, quarter=1): (
            f"1001|Example Target Inc.|DEFM14A|2026-01-05|{proxy_path}\n"
            f"1001|Example Target Inc.|10-Q|2026-01-05|{later_cover_path}\n"
            f"1001|Example Target Inc.|8-K|2026-01-13|{resolution_path}\n"
        ),
        archive.format(path=cover_path): (
            "<ACCEPTANCE-DATETIME>20251101120000\n"
            "<dei:TradingSymbol>OLD</dei:TradingSymbol>"
        ),
        archive.format(path=proxy_path): (
            "<ACCEPTANCE-DATETIME>20260105160000\n"
            "Buyer common stock is listed under the symbol BUY. "
            "The company entered into an Agreement and Plan of Merger. "
            "Holders will receive $100.00 in cash per share."
        ),
        archive.format(path=resolution_path): (
            "<ACCEPTANCE-DATETIME>20260113160000\n"
            "The parties terminated the merger agreement."
        ),
        archive.format(path=later_cover_path): (
            "<ACCEPTANCE-DATETIME>20260105170000\n"
            "<dei:TradingSymbol>FUTURE</dei:TradingSymbol>"
        ),
    }
    monkeypatch.setattr(
        requests,
        "Session",
        lambda: _EdgarSession(pages),
    )
    source = SecCashMergerEventSource(
        tmp_path / "events",
        client=EdgarMasterIndexClient(
            minimum_request_interval_seconds=0.0,
        ),
    )

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    snapshot = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert len(snapshot.events) == 2
    assert (snapshot.events[0].target_symbol, snapshot.events[0].status) == ("OLD", "pending")
    assert (snapshot.events[1].target_symbol, snapshot.events[1].status) == (
        "OLD",
        "terminated",
    )


def test_edgar_source_uses_the_proxy_ticker_disclosure_without_a_cover_lookup(
    tmp_path, monkeypatch
) -> None:
    index = "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx"
    proxy_path = "edgar/data/1001/0002.txt"
    pages = {
        index: f"1001|Example Target Inc.|DEFM14A|2026-01-05|{proxy_path}\n",
        f"https://www.sec.gov/Archives/{proxy_path}": (
            "<ACCEPTANCE-DATETIME>20260105160000\n"
            "Common stock is listed on Nasdaq under the symbol &#8220;TGTX&#8221;. "
            "The company entered into an Agreement and Plan of Merger. "
            "Holders will receive $100.00 in cash per share."
        ),
    }
    monkeypatch.setattr(requests, "Session", lambda: _EdgarSession(pages))
    source = SecCashMergerEventSource(
        tmp_path / "events",
        client=EdgarMasterIndexClient(
            minimum_request_interval_seconds=0.0,
        ),
    )

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    snapshot = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert snapshot.events[0].target_symbol == "TGTX"


def test_edgar_source_selects_latest_eligible_cover_by_acceptance_time(
    tmp_path, monkeypatch
) -> None:
    index = "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx"
    older_cover_path = "edgar/data/1001/z-older.txt"
    newer_cover_path = "edgar/data/1001/a-newer.txt"
    proxy_path = "edgar/data/1001/proxy.txt"
    pages = {
        index: (
            f"1001|Example Target Inc.|10-Q|2026-01-05|{older_cover_path}\n"
            f"1001|Example Target Inc.|10-Q|2026-01-05|{newer_cover_path}\n"
            f"1001|Example Target Inc.|DEFM14A|2026-01-05|{proxy_path}\n"
        ),
        f"https://www.sec.gov/Archives/{older_cover_path}": (
            "<ACCEPTANCE-DATETIME>20260105140000\n"
            "<dei:TradingSymbol>OLD</dei:TradingSymbol>"
        ),
        f"https://www.sec.gov/Archives/{newer_cover_path}": (
            "<ACCEPTANCE-DATETIME>20260105150000\n"
            "<dei:TradingSymbol>NEW</dei:TradingSymbol>"
        ),
        f"https://www.sec.gov/Archives/{proxy_path}": (
            "<ACCEPTANCE-DATETIME>20260105160000\n"
            "The company entered into an Agreement and Plan of Merger. "
            "Holders will receive $100.00 in cash per share."
        ),
    }
    monkeypatch.setattr(requests, "Session", lambda: _EdgarSession(pages))
    source = SecCashMergerEventSource(
        tmp_path / "events",
        client=EdgarMasterIndexClient(
            minimum_request_interval_seconds=0.0,
        ),
    )

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    snapshot = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert snapshot.events[0].target_symbol == "NEW"


def test_edgar_source_closes_symbol_lineage_after_resolution(tmp_path, monkeypatch) -> None:
    index = "https://www.sec.gov/Archives/edgar/full-index/2026/QTR1/master.idx"
    discovery_path = "edgar/data/1001/z-discovery.txt"
    termination_path = "edgar/data/1001/a-termination.txt"
    stale_follow_up_path = "edgar/data/1001/m-stale-follow-up.txt"
    pages = {
        index: (
            f"1001|Example Target Inc.|DEFM14A|2026-01-05|{discovery_path}\n"
            f"1001|Example Target Inc.|8-K|2026-01-05|{termination_path}\n"
            f"1001|Example Target Inc.|8-K|2026-01-05|{stale_follow_up_path}\n"
        ),
        f"https://www.sec.gov/Archives/{discovery_path}": (
            "<ACCEPTANCE-DATETIME>20260105160000\n"
            "Common stock is listed under the symbol TGTX. "
            "The company entered into an Agreement and Plan of Merger. "
            "Holders will receive $100.00 in cash per share."
        ),
        f"https://www.sec.gov/Archives/{termination_path}": (
            "<ACCEPTANCE-DATETIME>20260105170000\n"
            "The parties terminated the merger agreement."
        ),
        f"https://www.sec.gov/Archives/{stale_follow_up_path}": (
            "<ACCEPTANCE-DATETIME>20260105180000\n"
            "The company entered into a definitive merger agreement. "
            "Holders will receive $120.00 in cash per share."
        ),
    }
    monkeypatch.setattr(requests, "Session", lambda: _EdgarSession(pages))
    source = SecCashMergerEventSource(
        tmp_path / "events",
        client=EdgarMasterIndexClient(
            minimum_request_interval_seconds=0.0,
        ),
    )

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    snapshot = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert len(snapshot.events) == 2
    assert snapshot.events[0].status == "pending"
    assert snapshot.events[1].status == "terminated"


def test_immutable_snapshot_identity_preserves_extended_coverage(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_Filings())

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    source.refresh(date(2026, 1, 1), date(2026, 1, 20))
    extended = source.load_cached(date(2026, 1, 1), date(2026, 1, 20))

    assert len(tuple((tmp_path / "events").glob("cash-merger-events-*.json"))) == 2
    assert source.latest().covered_end == extended.covered_end == "2026-01-20"


def test_event_source_load_cached_never_contacts_edgar(tmp_path) -> None:
    live = SecCashMergerEventSource(tmp_path / "events", client=_Filings())
    live.refresh(date(2026, 1, 1), date(2026, 1, 15))
    cached = SecCashMergerEventSource(tmp_path / "events", client=_UnavailableFilings())

    snapshot = cached.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert snapshot.covered_start == "2026-01-01"
    assert snapshot.covered_end == "2026-01-15"


def test_event_source_selects_the_newest_snapshot_that_covers_the_requested_range(
    tmp_path,
) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_Filings())
    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    covering = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))
    source.refresh(date(2026, 1, 10), date(2026, 1, 20))

    selected = source.load_cached(date(2026, 1, 1), date(2026, 1, 15))

    assert selected.source_sha256 == covering.source_sha256


def test_ecb_source_converts_usd_offers_to_eur_and_reuses_cache(tmp_path) -> None:
    source = EcbUsdEurSource(tmp_path / "fx", client=_Fx())

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    live = EcbUsdEurSource(tmp_path / "fx").load_cached(
        date(2026, 1, 1), date(2026, 1, 15)
    )
    cached = EcbUsdEurSource(tmp_path / "fx").load_cached(
        date(2026, 1, 1), date(2026, 1, 15)
    )

    assert live.eur_per_usd.iloc[0] == 0.8
    assert cached.eur_per_usd.equals(live.eur_per_usd)

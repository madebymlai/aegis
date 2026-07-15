from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
import requests

from research.aegis_research.external_data.ecb_fx import EcbUsdEurSource
from research.aegis_research.external_data.sec_cash_mergers import (
    CashMergerSourceError,
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


class _Fx:
    def usd_per_eur(self, start: date, end: date) -> pd.Series:
        return pd.Series(
            [1.25, 1.20],
            index=pd.to_datetime([start.isoformat(), end.isoformat()]),
        )


def test_event_source_preserves_each_causal_filing_and_uses_validated_offline_cache(
    tmp_path,
) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_Filings())

    live = source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    cached = SecCashMergerEventSource(
        tmp_path / "events", client=_UnavailableFilings()
    ).load(date(2026, 1, 1), date(2026, 1, 15), refresh=True)

    assert [(event.status, event.offer_price) for event in live.events] == [
        ("pending", 100.0),
        ("pending", 110.0),
        ("terminated", None),
    ]
    assert cached.events == live.events
    assert live.events[0].available_at == "2026-01-05T16:00:00+00:00"
    assert live.events[0].source_url.endswith("/0001.txt")
    assert live.source_sha256


def test_event_source_fails_clearly_without_live_data_or_cache(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "empty", client=_UnavailableFilings())

    with pytest.raises(CashMergerSourceError, match="cache is empty"):
        source.load(date(2026, 1, 1), date(2026, 1, 15), refresh=True)


def test_immutable_snapshot_identity_preserves_extended_coverage(tmp_path) -> None:
    source = SecCashMergerEventSource(tmp_path / "events", client=_Filings())

    source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    extended = source.refresh(date(2026, 1, 1), date(2026, 1, 20))

    assert len(tuple((tmp_path / "events").glob("cash-merger-events-*.json"))) == 2
    assert source.latest().covered_end == extended.covered_end == "2026-01-20"


def test_ecb_source_converts_usd_offers_to_eur_and_reuses_cache(tmp_path) -> None:
    source = EcbUsdEurSource(tmp_path / "fx", client=_Fx())

    live = source.refresh(date(2026, 1, 1), date(2026, 1, 15))
    cached = EcbUsdEurSource(tmp_path / "fx").load(
        date(2026, 1, 1), date(2026, 1, 15), refresh=False
    )

    assert live.eur_per_usd.iloc[0] == 0.8
    assert cached.eur_per_usd.equals(live.eur_per_usd)

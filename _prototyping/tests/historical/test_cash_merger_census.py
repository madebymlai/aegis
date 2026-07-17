from __future__ import annotations

from datetime import date

from cash_merger.census import (
    CashMergerCensusSource,
    CashMergerEvent,
    ReferenceDeal,
    assemble_deals,
)
from cash_merger.ditat import DitatPendingCashReferenceSource
from cash_merger.eligibility import DomesticIssuerReferenceSource
from cash_merger.massive import (
    MassiveCashMergerEventSource,
    PricePoint,
    _non_cash_consideration,
    _offer,
)
from cash_merger.target_events import MassiveTargetEventSource


class _Events:
    def events(self, start: date, end: date):
        return (
            CashMergerEvent(
                target_cik="1001",
                target_name="Example Target, Inc.",
                target_symbol="OLD",
                status="pending",
                available_at="2024-01-05T21:00:00+00:00",
                offer_price=100.0,
                source_form="8-K",
                source_url="https://www.sec.gov/Archives/one.txt",
                accession="one",
            ),
            CashMergerEvent(
                target_cik="1001",
                target_name="Example Target, Inc.",
                target_symbol="OLD",
                status="pending",
                available_at="2024-02-01T21:00:00+00:00",
                offer_price=105.0,
                source_form="8-K/A",
                source_url="https://www.sec.gov/Archives/two.txt",
                accession="two",
            ),
            CashMergerEvent(
                target_cik="1001",
                target_name="Example Target, Inc.",
                target_symbol="OLD",
                status="completed",
                available_at="2024-03-15T21:00:00+00:00",
                offer_price=None,
                source_form="8-K",
                source_url="https://www.sec.gov/Archives/three.txt",
                accession="three",
            ),
            CashMergerEvent(
                target_cik="1001",
                target_name="Example Target, Inc.",
                target_symbol="NEW",
                status="pending",
                available_at="2025-04-01T21:00:00+00:00",
                offer_price=80.0,
                source_form="8-K",
                source_url="https://www.sec.gov/Archives/four.txt",
                accession="four",
            ),
            CashMergerEvent(
                target_cik="1001",
                target_name="Example Target, Inc.",
                target_symbol="NEW",
                status="terminated",
                available_at="2025-06-01T21:00:00+00:00",
                offer_price=None,
                source_form="8-K",
                source_url="https://www.sec.gov/Archives/five.txt",
                accession="five",
            ),
        )


class _References:
    def deals(self, start: date, end: date):
        return (
            ReferenceDeal(
                target_name="Example Target Inc",
                acquirer_name="First Buyer LLC",
                announced_on=date(2024, 1, 4),
                source_url="https://example.test/reference-one",
            ),
            ReferenceDeal(
                target_name="Example Target Incorporated",
                acquirer_name="Second Buyer LLC",
                announced_on=date(2025, 3, 31),
                source_url="https://example.test/reference-two",
            ),
            ReferenceDeal(
                target_name="Missing Target Corp",
                acquirer_name="Third Buyer LLC",
                announced_on=date(2025, 7, 1),
                source_url="https://example.test/reference-three",
            ),
        )


class _UnavailableEvents:
    def events(self, start: date, end: date):
        raise AssertionError("a covering cache hit must not contact the event source")


class _UnavailableReferences:
    def deals(self, start: date, end: date):
        raise AssertionError("a covering cache hit must not contact the reference source")


def test_census_assembles_one_immutable_record_for_each_announced_deal(tmp_path) -> None:
    source = CashMergerCensusSource(tmp_path, events=_Events(), references=_References())

    snapshot = source.sync(date(2024, 1, 1), date(2025, 12, 31))

    assert len(snapshot.deals) == 2
    assert snapshot.deals[0].deal_id == "1001:one"
    assert snapshot.deals[0].initial_offer_price == 100.0
    assert snapshot.deals[0].latest_offer_price == 105.0
    assert snapshot.deals[0].outcome == "completed"
    assert snapshot.deals[0].announcement_symbol == "OLD"
    assert snapshot.deals[0].accessions == ("one", "two", "three")
    assert snapshot.deals[1].deal_id == "1001:four"
    assert snapshot.deals[1].outcome == "terminated"


def test_census_coverage_reports_only_unambiguous_reference_matches(tmp_path) -> None:
    source = CashMergerCensusSource(tmp_path, events=_Events(), references=_References())

    snapshot = source.sync(date(2024, 1, 1), date(2025, 12, 31))

    assert snapshot.audit.reference_deals == 3
    assert snapshot.audit.matched_reference_deals == 2
    assert snapshot.audit.coverage == 2 / 3
    assert snapshot.audit.unmatched_targets == ("Missing Target Corp",)
    assert snapshot.audit.passes(0.90) is False


def test_census_reuses_a_content_addressed_covering_snapshot_without_network(tmp_path) -> None:
    live = CashMergerCensusSource(tmp_path, events=_Events(), references=_References())
    live_snapshot = live.sync(date(2024, 1, 1), date(2025, 12, 31))
    cached = CashMergerCensusSource(
        tmp_path,
        events=_UnavailableEvents(),
        references=_UnavailableReferences(),
    )

    cached_snapshot = cached.sync(date(2024, 1, 1), date(2025, 12, 31))

    assert cached_snapshot == live_snapshot
    assert len(tuple(tmp_path.glob("cash-merger-census-*.json"))) == 1


def test_census_does_not_include_observations_after_the_requested_end(tmp_path) -> None:
    source = CashMergerCensusSource(tmp_path, events=_Events(), references=_References())

    snapshot = source.sync(date(2024, 1, 1), date(2024, 12, 31))

    assert len(snapshot.deals) == 1
    assert snapshot.deals[0].outcome == "completed"
    assert snapshot.deals[0].resolved_at == "2024-03-15T21:00:00+00:00"


def test_one_filing_can_terminate_old_deal_and_announce_replacement() -> None:
    events = (
        CashMergerEvent(
            target_cik="1001",
            target_name="Target",
            target_symbol="TGT",
            status="pending",
            available_at="2025-01-01T23:59:59+00:00",
            offer_price=10.0,
            source_form="8-K",
            source_url="https://example.test/old",
            accession="old",
        ),
        CashMergerEvent(
            target_cik="1001",
            target_name="Target",
            target_symbol="TGT",
            status="terminated",
            available_at="2025-02-01T23:59:59+00:00",
            offer_price=None,
            source_form="8-K",
            source_url="https://example.test/switch",
            accession="switch",
        ),
        CashMergerEvent(
            target_cik="1001",
            target_name="Target",
            target_symbol="TGT",
            status="pending",
            available_at="2025-02-01T23:59:59+00:00",
            offer_price=12.0,
            source_form="8-K",
            source_url="https://example.test/switch",
            accession="switch",
        ),
    )

    deals = assemble_deals(events)

    assert [(deal.initial_offer_price, deal.outcome) for deal in deals] == [
        (10.0, "terminated"),
        (12.0, "pending"),
    ]


class _MassiveDisclosures:
    def disclosures(self, category: str, start: date, end: date):
        rows = {
            "merger_agreement": (
                {
                    "cik": "0001001",
                    "company_name": "Example Target Inc.",
                    "tickers": ["TGT"],
                    "filing_date": "2025-01-05",
                    "accession_number": "agreement-one",
                    "supporting_text": (
                        "The company entered into an Agreement and Plan of Merger. "
                        "Each share will receive $100.00 per share in cash."
                    ),
                },
                {
                    "cik": "0002001",
                    "company_name": "Example Buyer Inc.",
                    "tickers": ["BUY"],
                    "filing_date": "2025-01-05",
                    "accession_number": "buyer-agreement",
                    "supporting_text": (
                        "The company entered into an Agreement and Plan of Merger. "
                        "Each target share will receive $100.00 per share in cash."
                    ),
                },
                {
                    "cik": "0001002",
                    "company_name": "Mixed Target Inc.",
                    "tickers": ["MIX"],
                    "filing_date": "2025-01-06",
                    "accession_number": "agreement-two",
                    "supporting_text": (
                        "Each share will receive $10.00 and one share of buyer stock "
                        "as stock-and-cash consideration."
                    ),
                },
            ),
            "acquisition_agreement": (),
            "merger_completion": (
                {
                    "cik": "0001001",
                    "company_name": "Example Target Inc.",
                    "tickers": ["TGT"],
                    "filing_date": "2025-03-10",
                    "accession_number": "completion-one",
                    "supporting_text": "The company completed the merger transaction.",
                },
            ),
            "acquisition_completion": (),
            "deal_termination": (),
            "deal_withdrawal": (),
            "deal_breach_default": (),
        }
        return rows[category]

    def daily_closes(self, ticker: str, start: date, end: date):
        history = {
            "TGT": (
                *(PricePoint(date(2024, 12, day), 70.0 + (day % 2)) for day in range(16, 28)),
                PricePoint(date(2025, 1, 6), 95.0),
            ),
            "BUY": (
                *(PricePoint(date(2024, 12, day), 350.0 + (day % 2)) for day in range(16, 28)),
                PricePoint(date(2025, 1, 6), 355.0),
            ),
        }
        return history.get(ticker, ())

    def filing_text(self, accession: str, cik: str, filed_on: date):
        texts = {
            "agreement-one": (
                "The target entered into a merger agreement. Each share will receive "
                "$100.00 per share in cash."
            ),
            "buyer-agreement": (
                "The buyer entered into a merger agreement. Each target share will "
                "receive $100.00 per share in cash."
            ),
        }
        return texts.get(accession)


def test_massive_provider_builds_only_linked_fixed_cash_lifecycles(tmp_path) -> None:
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveCashMergerEventSource(_MassiveDisclosures()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 1, 1), date(2025, 12, 31))

    assert len(snapshot.deals) == 1
    assert snapshot.deals[0].target_cik == "1001"
    assert snapshot.deals[0].announcement_symbol == "TGT"
    assert snapshot.deals[0].initial_offer_price == 100.0
    assert snapshot.deals[0].outcome == "completed"
    assert snapshot.deals[0].accessions == ("agreement-one", "completion-one")


def test_massive_date_only_disclosure_is_not_available_during_filing_day(tmp_path) -> None:
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveCashMergerEventSource(_MassiveDisclosures()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 1, 1), date(2025, 12, 31))

    assert snapshot.deals[0].announced_at == "2025-01-05T23:59:59.999999+00:00"


class _ParValueDisclosures:
    def disclosures(self, category: str, start: date, end: date):
        if category != "merger_agreement":
            return ()
        return (
            {
                "cik": "0003001",
                "tickers": ["PAR"],
                "filing_date": "2025-08-19",
                "accession_number": "par-value-agreement",
                "supporting_text": (
                    "The Merger Agreement provides that each share of common stock, "
                    "par value $1.00 per share, will be converted into the right to "
                    "receive $22.00 per share in cash."
                ),
            },
        )

    def filing_text(self, accession: str, cik: str, filed_on: date):
        return (
            "Each share of common stock, par value $1.00 per share, will be converted "
            "into the right to receive $22.00 per share in cash under the merger agreement."
        )

    def daily_closes(self, ticker: str, start: date, end: date):
        return (
            *(PricePoint(date(2025, 8, day), 16.0) for day in range(1, 13)),
            PricePoint(date(2025, 8, 20), 21.0),
        )


class _StockConsiderationDisclosures(_ParValueDisclosures):
    def disclosures(self, category: str, start: date, end: date):
        if category != "merger_agreement":
            return ()
        return (
            {
                "cik": "0003002",
                "tickers": ["STK"],
                "filing_date": "2025-08-19",
                "accession_number": "stock-agreement",
                "supporting_text": "The transaction is valued at $41.37 per share in cash.",
            },
        )

    def filing_text(self, accession: str, cik: str, filed_on: date):
        return (
            "The merger consideration is an exchange ratio of 1.25 shares of Parent "
            "common stock for each Company share."
        )


def test_massive_provider_does_not_parse_par_value_as_the_cash_offer(tmp_path) -> None:
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveCashMergerEventSource(_ParValueDisclosures()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 8, 1), date(2025, 12, 31))

    assert len(snapshot.deals) == 1
    assert snapshot.deals[0].initial_offer_price == 22.0


def test_massive_provider_rejects_stock_terms_hidden_outside_the_excerpt(tmp_path) -> None:
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveCashMergerEventSource(_StockConsiderationDisclosures()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 8, 1), date(2025, 12, 31))

    assert snapshot.deals == ()


def test_equity_award_conversion_does_not_reclassify_cash_share_consideration() -> None:
    text = (
        "Each common share will be converted into the right to receive $231.00 in cash. "
        "Each employee RSU will later be converted into an award using an exchange ratio."
    )

    assert _offer(text) == 231.0
    assert _non_cash_consideration(text) is False


def test_offer_consensus_ignores_unrelated_preferred_dividend_amount() -> None:
    text = (
        "Each common share, par value $0.01 per share, will be converted into the right "
        "to receive $70.00 per share, net in cash, as the merger consideration. "
        "The company may pay a $412.50 preferred-stock dividend before closing."
    )

    assert _offer(text) == 70.0


def test_offer_parses_amount_in_cash_equal_to_wording() -> None:
    text = (
        "Each common share shall be converted into the right to receive an amount in "
        "cash equal to $31.00, without interest."
    )

    assert _offer(text) == 31.0


class _TargetEvents:
    def filing_index(self, form_type: str, start: date, end: date):
        return ()

    def disclosures(self, category: str, start: date, end: date):
        rows = {
            "merger_agreement": (
                {
                    "cik": "0004001",
                    "company_name": "Example Target Inc.",
                    "tickers": ["TGT"],
                    "filing_date": "2025-01-05",
                    "accession_number": "target-announcement",
                    "supporting_text": (
                        "The Company entered into a merger agreement with Parent and "
                        "Merger Sub. Merger Sub will merge with and into the Company, "
                        "with the Company surviving as a wholly-owned subsidiary of Parent."
                    ),
                },
                {
                    "cik": "0004002",
                    "company_name": "Example Buyer Inc.",
                    "tickers": ["BUY"],
                    "filing_date": "2025-01-05",
                    "accession_number": "buyer-announcement",
                    "supporting_text": (
                        "Example Buyer Inc. ('Parent' or 'BUY') entered into a merger "
                        "agreement with Target Corp. Merger Sub will merge with and into "
                        "Target Corp., with Target Corp. surviving."
                    ),
                },
            ),
            "acquisition_agreement": (),
            "merger_completion": (
                {
                    "cik": "0004001",
                    "tickers": ["TGT"],
                    "filing_date": "2025-03-10",
                    "accession_number": "target-completion",
                    "supporting_text": "The Company completed the merger transaction.",
                },
            ),
            "acquisition_completion": (),
            "deal_termination": (),
            "deal_withdrawal": (),
            "deal_breach_default": (),
        }
        return rows[category]

    def filing_texts_many(self, ciks, start: date, end: date):
        assert set(ciks) == {"4001"}
        return (
            {
                "cik": "0004001",
                "filing_date": "2025-01-05",
                "accession_number": "target-announcement",
                "items_text": (
                    "Each share will receive $100.00 per share in cash under the merger."
                ),
            },
        )


def test_target_role_discovery_excludes_acquirer_and_builds_lifecycle(tmp_path) -> None:
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveTargetEventSource(_TargetEvents()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 1, 1), date(2025, 12, 31))

    assert len(snapshot.deals) == 1
    assert snapshot.deals[0].announcement_symbol == "TGT"
    assert snapshot.deals[0].announced_at == "2025-01-05T23:59:59.999999+00:00"
    assert snapshot.deals[0].initial_offer_price == 100.0
    assert snapshot.deals[0].outcome == "completed"
    assert snapshot.deals[0].accessions == ("target-announcement", "target-completion")


class _ProxyConfirmedTargetEvents(_TargetEvents):
    def disclosures(self, category: str, start: date, end: date):
        if category == "merger_agreement":
            return (
                {
                    "cik": "0004003",
                    "tickers": ["OLD", "NEW"],
                    "filing_date": "2025-04-01",
                    "accession_number": "offer-only-announcement",
                    "supporting_text": (
                        "Each outstanding share will be converted into the right to "
                        "receive $70.00 per share, net in cash."
                    ),
                },
            )
        return ()

    def filing_index(self, form_type: str, start: date, end: date):
        if form_type != "DEFM14A":
            return ()
        return (
            {
                "cik": "0004003",
                "ticker": "NEW",
                "issuer_name": "Renamed Target Inc.",
                "filing_date": "2025-05-01",
                "accession_number": "target-proxy",
            },
        )

    def filing_texts_many(self, ciks, start: date, end: date):
        assert set(ciks) == {"4003"}
        return (
            {
                "cik": "0004003",
                "filing_date": "2025-04-01",
                "accession_number": "offer-only-announcement",
                "items_text": (
                    "Each outstanding share will be converted into the right to "
                    "receive $70.00 per share, net in cash."
                ),
            },
        )


def test_proxy_confirms_offer_only_target_and_selects_current_common_ticker(tmp_path) -> None:
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveTargetEventSource(_ProxyConfirmedTargetEvents()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 1, 1), date(2025, 12, 31))

    assert len(snapshot.deals) == 1
    assert snapshot.deals[0].announcement_symbol == "NEW"
    assert snapshot.deals[0].initial_offer_price == 70.0


def test_full_text_first_party_company_role_confirms_recent_target(tmp_path) -> None:
    class _RecentTarget(_TargetEvents):
        def disclosures(self, category: str, start: date, end: date):
            if category == "merger_agreement":
                return (
                    {
                        "cik": "0004004",
                        "tickers": ["NEW"],
                        "filing_date": "2025-07-01",
                        "accession_number": "recent-target",
                        "supporting_text": (
                            "Each share will be converted into the right to receive "
                            "$85.00 per share in cash."
                        ),
                    },
                )
            return ()

        def filing_texts_many(self, ciks, start: date, end: date):
            return (
                {
                    "cik": "0004004",
                    "filing_date": "2025-07-01",
                    "accession_number": "recent-target",
                    "items_text": (
                        'Recent Target, Inc., a Delaware corporation (the "Company"), '
                        'Buyer Inc. ("Parent"), and Merger Sub entered into a merger '
                        "agreement. Merger Sub will be merged with and into the Company, "
                        "with the Company surviving as a wholly owned subsidiary of Parent. "
                        "Each share will be converted into the right to receive $85.00 "
                        "per share in cash."
                    ),
                },
            )

    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveTargetEventSource(_RecentTarget()),
        references=_References(),
    )

    snapshot = source.sync(date(2025, 1, 1), date(2025, 12, 31))

    assert len(snapshot.deals) == 1
    assert snapshot.deals[0].announcement_symbol == "NEW"
    assert snapshot.deals[0].initial_offer_price == 85.0


class _DitatResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return (
            rb'<script>self.__next_f.push([1,"[{\"ticker\":\"TGT\",'
            rb"\"target\":\"Example Target, Inc.\","
            rb"\"acquirer\":\"Buyer LLC\",\"type\":\"cash\","
            rb"\"sourceUrl\":\"https://example.test/tgt\"},"
            rb"{\"ticker\":\"MIX\",\"target\":\"Mixed Target\","
            rb"\"acquirer\":\"Buyer LLC\",\"type\":\"mixed\","
            rb'\"sourceUrl\":\"https://example.test/mix\"}]"])</script>'
        )


def test_current_reference_audit_uses_cash_target_tickers_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _DitatResponse())
    source = CashMergerCensusSource(
        tmp_path,
        events=MassiveCashMergerEventSource(_MassiveDisclosures()),
        references=DitatPendingCashReferenceSource(),
    )

    snapshot = source.sync(date(2025, 1, 1), date(2025, 2, 1))

    assert snapshot.audit.reference_deals == 1
    assert snapshot.audit.matched_reference_deals == 1
    assert snapshot.audit.coverage == 1.0


def test_reference_eligibility_uses_independent_domestic_filing_status() -> None:
    class _CandidateReferences:
        def deals(self, start: date, end: date):
            return (
                ReferenceDeal("Domestic Target", "Buyer", "domestic", target_symbol="DOM"),
                ReferenceDeal("Foreign Target", "Buyer", "foreign", target_symbol="FPI"),
            )

    class _Filings:
        def filing_index_tickers(self, tickers, form_type, start: date, end: date):
            assert set(tickers) == {"DOM", "FPI"}
            assert form_type == "10-K"
            return ({"ticker": "DOM", "form_type": "10-K"},)

    references = DomesticIssuerReferenceSource(_CandidateReferences(), _Filings())

    eligible = references.deals(date(2025, 1, 1), date(2025, 12, 31))

    assert tuple(reference.target_symbol for reference in eligible) == ("DOM",)

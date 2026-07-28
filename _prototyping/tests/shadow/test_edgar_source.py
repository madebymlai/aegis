from datetime import UTC, date, datetime

from _prototyping.merger.shadow import (
    EdgarEventSource,
    EdgarFiling,
    IssuerIdentity,
)


def _submission(*, agreement_date: str, offer_price: str) -> bytes:
    return f"""<SEC-DOCUMENT>
<DOCUMENT><TYPE>8-K<TEXT>
The company entered into a definitive merger agreement. Each share will receive
${offer_price} per share in cash, without interest.
</TEXT></DOCUMENT>
<DOCUMENT><TYPE>EX-2.1<TEXT>
AGREEMENT AND PLAN OF MERGER dated as of {agreement_date}.
Each share shall be converted into the right to receive ${offer_price} per share in cash.
</TEXT></DOCUMENT>
</SEC-DOCUMENT>""".encode()


class _Gateway:
    def resolve(self, instrument_ids: tuple[str, ...]) -> tuple[IssuerIdentity, ...]:
        return (
            IssuerIdentity("D01.XNAS", "D01", "1"),
            IssuerIdentity("D02.XNYS", "D02", "2"),
        )

    def filings(
        self,
        *,
        start: date,
        end: date,
        ciks: frozenset[str],
    ) -> tuple[EdgarFiling, ...]:
        return (
            EdgarFiling(
                accession="0000000001-26-000001",
                cik="1",
                filed_at=datetime(2026, 1, 3, 12, tzinfo=UTC),
                form="8-K",
                source_url="https://www.sec.gov/Archives/d01",
                submission=_submission(agreement_date="January 2, 2026", offer_price="10.20"),
            ),
            EdgarFiling(
                accession="0000000002-26-000001",
                cik="2",
                filed_at=datetime(2026, 1, 4, 12, tzinfo=UTC),
                form="8-K",
                source_url="https://www.sec.gov/Archives/d02",
                submission=_submission(agreement_date="January 3, 2026", offer_price="20.40"),
            ),
            EdgarFiling(
                accession="0000000003-26-000001",
                cik="3",
                filed_at=datetime(2026, 1, 4, 13, tzinfo=UTC),
                form="8-K",
                source_url="https://www.sec.gov/Archives/outside-universe",
                submission=_submission(agreement_date="January 3, 2026", offer_price="30.60"),
            ),
        )


class _GatewayWithFilings:
    def __init__(self, filings: tuple[EdgarFiling, ...]) -> None:
        self._filings = filings

    def resolve(self, instrument_ids: tuple[str, ...]) -> tuple[IssuerIdentity, ...]:
        return (IssuerIdentity("D01.XNAS", "D01", "1"),)

    def filings(
        self,
        *,
        start: date,
        end: date,
        ciks: frozenset[str],
    ) -> tuple[EdgarFiling, ...]:
        return self._filings


def test_configured_instruments_are_resolved_to_ciks_before_events_are_created() -> None:
    source = EdgarEventSource(
        ("D01.XNAS", "D02.XNYS"),
        gateway=_Gateway(),
    )

    refresh = source.refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 4),
        active_events=(),
    )

    assert tuple(
        (event.instrument_id, event.target_cik, event.ticker, event.offer_price)
        for event in refresh.observations
    ) == (
        ("D01.XNAS", "1", "D01", 10.20),
        ("D02.XNYS", "2", "D02", 20.40),
    )
    assert refresh.reviews == ()


def test_equity_award_exchange_ratio_does_not_hide_fixed_cash_common_share_offer() -> None:
    filing = EdgarFiling(
        accession="0000000001-26-000002",
        cik="1",
        filed_at=datetime(2026, 1, 5, 12, tzinfo=UTC),
        form="8-K",
        source_url="https://www.sec.gov/Archives/d01-cash",
        submission=b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The company entered into a definitive merger agreement. Each common share
        will be converted into the right to receive $25.00 in cash, without interest.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 4, 2026.
        Each common share will be converted into the right to receive $25.00 in cash.
        The option exchange ratio applies only to employee equity awards.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((filing,)),
    ).refresh(
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        active_events=(),
    )

    assert refresh.observations[0].offer_price == 25.00
    assert refresh.reviews == ()


def test_cash_plus_stock_common_share_offer_is_not_a_fixed_cash_event() -> None:
    filing = EdgarFiling(
        accession="0000000001-26-000003",
        cik="1",
        filed_at=datetime(2026, 1, 6, 12, tzinfo=UTC),
        form="8-K",
        source_url="https://www.sec.gov/Archives/d01-mixed",
        submission=b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Each common share will be converted into the right to receive $155.00 in cash
        and 0.772 shares of Buyer common stock.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 5, 2026.
        Each common share will be converted into the right to receive $155.00 in cash
        and 0.772 shares of Buyer common stock.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((filing,)),
    ).refresh(
        start=date(2026, 1, 6),
        end=date(2026, 1, 6),
        active_events=(),
    )

    assert refresh.observations == ()
    assert refresh.reviews[0].reason == "unique fixed-cash offer not extracted"


def test_cash_plus_contingent_value_right_is_not_a_fixed_cash_event() -> None:
    filing = EdgarFiling(
        accession="0000000001-26-000004",
        cik="1",
        filed_at=datetime(2026, 1, 7, 12, tzinfo=UTC),
        form="8-K",
        source_url="https://www.sec.gov/Archives/d01-cvr",
        submission=b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Each common share will be converted into the right to receive $17.00 in cash
        plus one contingent value right tied to regulatory milestones.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 6, 2026.
        Each common share will be converted into the right to receive $17.00 in cash
        plus one CVR.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((filing,)),
    ).refresh(
        start=date(2026, 1, 7),
        end=date(2026, 1, 7),
        active_events=(),
    )

    assert refresh.observations == ()
    assert refresh.reviews[0].reason == "unique fixed-cash offer not extracted"


def test_stock_before_cash_is_not_a_fixed_cash_event() -> None:
    filing = EdgarFiling(
        accession="0000000001-26-000005",
        cik="1",
        filed_at=datetime(2026, 1, 8, 12, tzinfo=UTC),
        form="8-K",
        source_url="https://www.sec.gov/Archives/d01-stock-first",
        submission=b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Each common share will be converted into the right to receive 0.5 shares of
        Buyer common stock plus $25.00 in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 7, 2026.
        Each common share will be converted into the right to receive 0.5 shares of
        Buyer common stock plus $25.00 in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((filing,)),
    ).refresh(
        start=date(2026, 1, 8),
        end=date(2026, 1, 8),
        active_events=(),
    )

    assert refresh.observations == ()
    assert refresh.reviews[0].reason == "unique fixed-cash offer not extracted"


def test_distant_stock_component_is_not_a_fixed_cash_event() -> None:
    filing = EdgarFiling(
        accession="0000000001-26-000006",
        cik="1",
        filed_at=datetime(2026, 1, 9, 12, tzinfo=UTC),
        form="8-K",
        source_url="https://www.sec.gov/Archives/d01-distant-stock",
        submission=b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Each common share will be converted into the right to receive $25.00 in cash,
        without interest and subject to the customary withholding provisions described
        in the agreement. The cash amount is payable at closing after surrender of the
        certificate, delivery of the transmittal materials, verification of ownership,
        and satisfaction of the other administrative procedures described below, plus
        0.5 shares of Buyer common stock.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 8, 2026.
        Each common share will be converted into the right to receive $25.00 in cash,
        without interest and subject to the customary withholding provisions described
        in the agreement. The cash amount is payable at closing after surrender of the
        certificate, delivery of the transmittal materials, verification of ownership,
        and satisfaction of the other administrative procedures described below, plus
        0.5 shares of Buyer common stock.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((filing,)),
    ).refresh(
        start=date(2026, 1, 9),
        end=date(2026, 1, 9),
        active_events=(),
    )

    assert refresh.observations == ()
    assert refresh.reviews[0].reason == "unique fixed-cash offer not extracted"


def test_same_agreement_in_multiple_filings_preserves_one_event_identity() -> None:
    first = EdgarFiling(
        accession="0000000001-26-000010",
        cik="1",
        filed_at=datetime(2026, 1, 10, 12, tzinfo=UTC),
        form="8-K",
        source_url="https://www.sec.gov/Archives/d01-first",
        submission=_submission(agreement_date="January 9, 2026", offer_price="10.20"),
        document_types=("8-K", "EX-2.1"),
    )
    amendment = EdgarFiling(
        accession="0000000001-26-000011",
        cik="1",
        filed_at=datetime(2026, 1, 10, 13, tzinfo=UTC),
        form="8-K/A",
        source_url="https://www.sec.gov/Archives/d01-amendment",
        submission=_submission(agreement_date="January 9, 2026", offer_price="10.20"),
        document_types=("8-K/A", "EX-2.1"),
    )

    refresh = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((first, amendment)),
    ).refresh(
        start=date(2026, 1, 10),
        end=date(2026, 1, 10),
        active_events=(),
    )

    assert tuple(event.event_id for event in refresh.observations) == (
        "1:0000000001-26-000010",
        "1:0000000001-26-000010",
    )
    assert tuple(event.status.value for event in refresh.observations) == (
        "announced",
        "amended",
    )

    replay = EdgarEventSource(
        ("D01.XNAS",),
        gateway=_GatewayWithFilings((first, amendment)),
    ).refresh(
        start=date(2026, 1, 10),
        end=date(2026, 1, 10),
        active_events=(refresh.observations[-1],),
    )

    assert {event.event_id for event in replay.observations} == {
        "1:0000000001-26-000010"
    }

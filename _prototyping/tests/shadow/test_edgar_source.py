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

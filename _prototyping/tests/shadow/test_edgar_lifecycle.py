from datetime import date, datetime

from _prototyping.merger.shadow import (
    EdgarEventSource,
    EdgarFiling,
    IssuerIdentity,
)

_ANNOUNCEMENT = b"""<SEC-DOCUMENT>
<DOCUMENT><TYPE>8-K<TEXT>
Deal One entered into a definitive merger agreement. Each share will receive
$10.20 per share in cash, without interest.
</TEXT></DOCUMENT>
<DOCUMENT><TYPE>EX-2.1<TEXT>
AGREEMENT AND PLAN OF MERGER dated as of January 2, 2026.
Each share shall be converted into the right to receive $10.20 per share in cash.
</TEXT></DOCUMENT>
</SEC-DOCUMENT>"""


class _Gateway:
    def __init__(self, filings: tuple[EdgarFiling, ...]) -> None:
        self._filings = filings

    def resolve(self, instrument_ids: tuple[str, ...]) -> tuple[IssuerIdentity, ...]:
        return (IssuerIdentity("D01.XNAS", "D01", "1"),)

    def filings(self, *, start, end, ciks) -> tuple[EdgarFiling, ...]:
        return self._filings


def _filing(
    accession: str,
    observed_at: str,
    submission: bytes,
    *,
    items: tuple[str, ...] = ("1.01",),
    document_types: tuple[str, ...] = (),
) -> EdgarFiling:
    return EdgarFiling(
        accession=accession,
        cik="1",
        filed_at=datetime.fromisoformat(observed_at),
        form="8-K",
        source_url=f"https://www.sec.gov/Archives/{accession}",
        submission=submission,
        items=items,
        document_types=document_types,
    )


def _source(*filings: EdgarFiling) -> EdgarEventSource:
    return EdgarEventSource(("D01.XNAS",), gateway=_Gateway(filings))


def _active_announcement():
    return _source(
        _filing(
            "0000000001-26-000001",
            "2026-01-03T12:00:00+00:00",
            _ANNOUNCEMENT,
            document_types=("8-K", "EX-2.1"),
        )
    ).refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 3),
        active_events=(),
    ).observations[0]


def test_unrelated_contract_termination_cannot_close_an_active_merger() -> None:
    active = _active_announcement()
    unrelated = _filing(
        "0000000001-26-000002",
        "2026-02-03T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>8-K<TEXT>
        Item 1.02. The company terminated an unrelated parking purchase agreement.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        items=("1.02",),
    )

    refresh = _source(unrelated).refresh(
        start=date(2026, 2, 3),
        end=date(2026, 2, 3),
        active_events=(active,),
    )

    assert refresh.observations == ()
    assert refresh.reviews[0].reason == "filing does not identify the active agreement"


def test_replacement_filing_closes_old_event_and_opens_new_event() -> None:
    active = _active_announcement()
    replacement = _filing(
        "0000000001-26-000003",
        "2026-02-18T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The Agreement and Plan of Merger dated as of January 2, 2026 was terminated.
        Deal One entered into a different merger agreement under which each share
        will receive $11.00 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of February 17, 2026.
        Each share shall be converted into the right to receive $11.00 per share in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        items=("1.01", "1.02"),
        document_types=("8-K", "EX-2.1"),
    )

    refresh = _source(replacement).refresh(
        start=date(2026, 2, 18),
        end=date(2026, 2, 18),
        active_events=(active,),
    )

    assert refresh.observations[0].event_id == active.event_id
    assert refresh.observations[0].status.value == "replaced"
    assert refresh.observations[1].event_id == "1:0000000001-26-000003"
    assert refresh.observations[1].status.value == "announced"


def test_amendment_preserves_identity_and_updates_terms() -> None:
    active = _active_announcement()
    amendment = _filing(
        "0000000001-26-000004",
        "2026-02-20T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Deal One amended its merger agreement. Each share will receive
        $10.40 per share in cash, without interest.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AMENDMENT TO AGREEMENT AND PLAN OF MERGER dated as of January 2, 2026.
        Each share shall be converted into the right to receive $10.40 per share in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = _source(amendment).refresh(
        start=date(2026, 2, 20),
        end=date(2026, 2, 20),
        active_events=(active,),
    )

    amended = refresh.observations[0]
    assert amended.event_id == active.event_id
    assert amended.instrument_id == "D01.XNAS"
    assert amended.agreement_accession == active.agreement_accession
    assert amended.offer_price == 10.40
    assert amended.status.value == "amended"


def test_cold_window_observes_completion_after_its_announcement() -> None:
    announcement = _filing(
        "0000000001-26-000001",
        "2026-01-03T12:00:00+00:00",
        _ANNOUNCEMENT,
        document_types=("8-K", "EX-2.1"),
    )
    completion = _filing(
        "0000000001-26-000005",
        "2026-01-09T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>8-K<TEXT>
        On January 9, 2026, the company completed the merger contemplated by the
        Agreement and Plan of Merger dated as of January 2, 2026.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        items=("2.01",),
    )

    refresh = _source(announcement, completion).refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 9),
        active_events=(),
    )

    assert tuple(observation.status.value for observation in refresh.observations) == (
        "announced",
        "completed",
    )

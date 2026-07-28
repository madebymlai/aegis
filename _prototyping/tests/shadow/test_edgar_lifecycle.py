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
    form: str = "8-K",
    items: tuple[str, ...] = ("1.01",),
    document_types: tuple[str, ...] = (),
) -> EdgarFiling:
    return EdgarFiling(
        accession=accession,
        cik="1",
        filed_at=datetime.fromisoformat(observed_at),
        form=form,
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


def test_non_lifecycle_filing_cannot_resolve_an_active_merger() -> None:
    active = _active_announcement()
    employment_agreement = _filing(
        "0000000001-26-000006",
        "2026-02-10T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>8-K<TEXT>
        Item 1.01. In connection with the Agreement and Plan of Merger dated as of
        January 2, 2026, executives signed employment agreements effective if the
        transaction is completed. Risks include payment of a termination fee pursuant
        to the Merger Agreement.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        items=("1.01", "5.02"),
    )

    refresh = _source(employment_agreement).refresh(
        start=date(2026, 2, 10),
        end=date(2026, 2, 10),
        active_events=(active,),
    )

    assert refresh.observations == ()
    assert refresh.reviews == ()


def test_conditional_termination_language_cannot_replace_an_active_merger() -> None:
    active = _active_announcement()
    separate_acquisition = _filing(
        "0000000001-26-000007",
        "2026-02-12T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The company entered a separate Agreement and Plan of Merger dated as of
        February 11, 2026 to acquire another business for an aggregate price.
        Its completion is conditioned on the prior transaction under the Agreement
        and Plan of Merger dated as of January 2, 2026. Either party may terminate
        this separate agreement if the January 2 Merger Agreement is validly terminated.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of February 11, 2026.
        This agreement may be terminated if the Agreement and Plan of Merger dated
        as of January 2, 2026 is validly terminated.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        items=("1.01", "9.01"),
        document_types=("8-K", "EX-2.1"),
    )

    refresh = _source(separate_acquisition).refresh(
        start=date(2026, 2, 12),
        end=date(2026, 2, 12),
        active_events=(active,),
    )

    assert refresh.observations == ()


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


def test_announcement_extracts_close_guidance_and_contractual_outside_date() -> None:
    filing = _filing(
        "0000000001-26-000008",
        "2026-01-03T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The transaction is expected to close in the second quarter of 2026.
        Each share will receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 2, 2026.
        Each share shall be converted into the right to receive $10.20 per share in cash.
        The Outside Date means September 30, 2026.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = _source(filing).refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 3),
        active_events=(),
    )

    timeline = refresh.observations[0].timeline
    assert timeline is not None
    assert timeline.guidance is not None
    assert timeline.guidance.earliest == "2026-04-01"
    assert timeline.guidance.latest == "2026-06-30"
    assert timeline.outside_date == "2026-09-30"


def test_guidance_accepts_close_by_end_of_quarter_wording() -> None:
    filing = _filing(
        "0000000001-26-000016",
        "2026-02-09T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The transaction is expected to close by the end of the third quarter of 2026.
        Each share will receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of February 8, 2026.
        Each share shall be converted into the right to receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    observation = _source(filing).refresh(
        start=date(2026, 2, 9),
        end=date(2026, 2, 9),
        active_events=(),
    ).observations[0]

    assert observation.timeline is not None
    assert observation.timeline.guidance is not None
    assert observation.timeline.guidance.earliest == "2026-07-01"
    assert observation.timeline.guidance.latest == "2026-09-30"


def test_guidance_accepts_completed_in_calendar_half_wording() -> None:
    active = _active_announcement()
    proxy = _filing(
        "0000000001-26-000017",
        "2026-07-09T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>PREM14A<TEXT>
        The parties currently expect the Merger to be completed in second half of
        calendar year 2026 under the Agreement and Plan of Merger dated as of
        January 2, 2026.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        form="PREM14A",
        items=(),
        document_types=("PREM14A",),
    )

    observation = _source(proxy).refresh(
        start=date(2026, 7, 9),
        end=date(2026, 7, 9),
        active_events=(active,),
    ).observations[0]

    assert observation.timeline is not None
    assert observation.timeline.guidance is not None
    assert observation.timeline.guidance.earliest == "2026-07-01"
    assert observation.timeline.guidance.latest == "2026-12-31"


def test_guidance_accepts_late_year_or_early_next_year_wording() -> None:
    active = _active_announcement()
    update = _filing(
        "0000000001-26-000018",
        "2026-06-26T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>8-K<TEXT>
        Under the Agreement and Plan of Merger dated as of January 2, 2026, the
        transaction is expected to close in late 2026 or early 2027.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        items=("8.01",),
    )

    observation = _source(update).refresh(
        start=date(2026, 6, 26),
        end=date(2026, 6, 26),
        active_events=(active,),
    ).observations[0]

    assert observation.timeline is not None
    assert observation.timeline.guidance is not None
    assert observation.timeline.guidance.earliest == "2026-10-01"
    assert observation.timeline.guidance.latest == "2027-03-31"


def test_guidance_accepts_mid_year_wording() -> None:
    filing = _filing(
        "0000000001-26-000020",
        "2026-06-15T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The transaction is expected to close in mid-2027.
        Each share will receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of June 12, 2026.
        Each share shall be converted into the right to receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    observation = _source(filing).refresh(
        start=date(2026, 6, 15),
        end=date(2026, 6, 15),
        active_events=(),
    ).observations[0]

    assert observation.timeline is not None
    assert observation.timeline.guidance is not None
    assert observation.timeline.guidance.earliest == "2027-04-01"
    assert observation.timeline.guidance.latest == "2027-09-30"


def test_proxy_vote_date_becomes_a_causal_nonterminal_timeline_milestone() -> None:
    active = _active_announcement()
    proxy = _filing(
        "0000000001-26-000009",
        "2026-04-10T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>DEFM14A<TEXT>
        A special meeting of stockholders will be held on May 15, 2026 to vote on
        the merger contemplated by the Agreement and Plan of Merger dated as of
        January 2, 2026.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        form="DEFM14A",
        items=(),
        document_types=("DEFM14A",),
    )

    refresh = _source(proxy).refresh(
        start=date(2026, 4, 10),
        end=date(2026, 4, 10),
        active_events=(active,),
    )

    observation = refresh.observations[0]
    assert observation.status.value == "amended"
    assert observation.event_id == active.event_id
    assert observation.timeline is not None
    assert observation.timeline.milestones[0].kind.value == "shareholder_vote"
    assert observation.timeline.milestones[0].scheduled_for == "2026-05-15"


def test_proxy_termination_boilerplate_cannot_resolve_an_active_merger() -> None:
    active = _active_announcement()
    proxy = _filing(
        "0000000001-26-000014",
        "2026-04-10T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>DEFM14A<TEXT>
        The Agreement and Plan of Merger dated as of January 2, 2026 may be
        terminated under specified circumstances. The transaction is expected to
        close in the second quarter of 2026.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        form="DEFM14A",
        items=(),
        document_types=("DEFM14A",),
    )

    refresh = _source(proxy).refresh(
        start=date(2026, 4, 10),
        end=date(2026, 4, 10),
        active_events=(active,),
    )

    assert len(refresh.observations) == 1
    assert refresh.observations[0].status.value == "amended"
    assert refresh.observations[0].timeline is not None


def test_solicitation_completion_wording_cannot_resolve_an_active_merger() -> None:
    active = _active_announcement()
    solicitation = _filing(
        "0000000001-26-000015",
        "2026-04-11T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>DEFA14A<TEXT>
        The presentation discusses a previously consummated transaction and the
        Agreement and Plan of Merger dated as of January 2, 2026.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        form="DEFA14A",
        items=(),
        document_types=("DEFA14A",),
    )

    refresh = _source(solicitation).refresh(
        start=date(2026, 4, 11),
        end=date(2026, 4, 11),
        active_events=(active,),
    )

    assert refresh.observations == ()
    assert refresh.reviews == ()


def test_outside_date_is_extracted_from_the_common_termination_clause() -> None:
    filing = _filing(
        "0000000001-26-000012",
        "2026-01-03T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        Each share will receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of January 2, 2026.
        Each share shall be converted into the right to receive $10.20 per share in cash.
        Either party may terminate if the merger has not been consummated on or before
        March 29, 2027 (the "Outside Date"), which date may be extended by up to 90 days.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    refresh = _source(filing).refresh(
        start=date(2026, 1, 3),
        end=date(2026, 1, 3),
        active_events=(),
    )

    assert refresh.observations[0].timeline is not None
    assert refresh.observations[0].timeline.outside_date == "2027-06-27"


def test_relative_outside_date_and_extension_are_computed_from_the_contract() -> None:
    filing = _filing(
        "0000000001-26-000019",
        "2026-06-17T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The transaction is expected to close in the third quarter of 2026.
        Each share will receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of June 16, 2026.
        Each share shall be converted into the right to receive $10.20 per share in cash.
        Either party may terminate if the Merger has not been consummated on or before
        the date that is 150 days after June 16, 2026 (the "Outside Date"), subject to
        a single 30-day extension in specified circumstances.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    observation = _source(filing).refresh(
        start=date(2026, 6, 17),
        end=date(2026, 6, 17),
        active_events=(),
    ).observations[0]

    assert observation.timeline is not None
    assert observation.timeline.outside_date == "2026-12-13"


def test_named_outside_date_with_parenthetical_extension_is_extracted() -> None:
    filing = _filing(
        "0000000001-26-000021",
        "2026-06-15T12:00:00+00:00",
        b"""<SEC-DOCUMENT>
        <DOCUMENT><TYPE>8-K<TEXT>
        The transaction is expected to close in mid-2027.
        Each share will receive $10.20 per share in cash.
        </TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-2.1<TEXT>
        AGREEMENT AND PLAN OF MERGER dated as of June 12, 2026.
        Each share shall be converted into the right to receive $10.20 per share in cash.
        Either party may terminate if the Merger shall not have been consummated on or
        before 11:59 p.m., New York City time, on June 12, 2027 (such time or such later
        time agreed in writing by the parties, the "Outside Date"); provided that the
        Outside Date shall automatically be extended for one additional three (3)-month
        period if regulatory approvals have not then been obtained.
        </TEXT></DOCUMENT>
        </SEC-DOCUMENT>""",
        document_types=("8-K", "EX-2.1"),
    )

    observation = _source(filing).refresh(
        start=date(2026, 6, 15),
        end=date(2026, 6, 15),
        active_events=(),
    ).observations[0]

    assert observation.timeline is not None
    assert observation.timeline.outside_date == "2027-09-12"


def test_ordinary_proxy_does_not_create_a_merger_review_item() -> None:
    active = _active_announcement()
    proxy = _filing(
        "0000000001-26-000013",
        "2026-04-10T12:00:00+00:00",
        b"""<SEC-DOCUMENT><DOCUMENT><TYPE>DEFM14A<TEXT>
        The annual meeting will elect directors and ratify the independent auditor.
        </TEXT></DOCUMENT></SEC-DOCUMENT>""",
        form="DEFM14A",
        items=(),
        document_types=("DEFM14A",),
    )

    refresh = _source(proxy).refresh(
        start=date(2026, 4, 10),
        end=date(2026, 4, 10),
        active_events=(active,),
    )

    assert refresh.observations == ()
    assert refresh.reviews == ()

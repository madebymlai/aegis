"""Behavior checks for causal deal-close estimation."""

from dataclasses import replace
from datetime import UTC, datetime

from _prototyping.merger.shadow import (
    CloseGuidance,
    DealTimeline,
    DealTimelineEvidence,
    EventObservation,
    EventStatus,
    TimelineMilestone,
    TimelineMilestoneKind,
)

_ANNOUNCEMENT = EventObservation(
    event_id="1:announcement",
    instrument_id="D01.XNYS",
    target_cik="1",
    ticker="D01",
    agreement_accession="announcement",
    agreement_date="2026-01-02",
    observed_at="2026-01-03T12:00:00+00:00",
    status=EventStatus.ANNOUNCED,
    offer_price=10.20,
    source_accession="announcement",
    source_url="https://example.test/announcement",
    evidence="Fixed-cash merger announced.",
    timeline=DealTimelineEvidence(
        guidance=CloseGuidance("2026-04-01", "2026-06-30"),
        outside_date="2026-09-30",
        milestones=(
            TimelineMilestone(
                TimelineMilestoneKind.SHAREHOLDER_VOTE,
                "2026-05-15",
            ),
        ),
    ),
)


def test_timeline_combines_guidance_outside_date_and_pending_milestones() -> None:
    estimate = DealTimeline().estimate(
        (_ANNOUNCEMENT,),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
    )

    assert estimate is not None
    assert estimate.announced_at == "2026-01-03T12:00:00+00:00"
    assert estimate.earliest_close == "2026-05-15"
    assert estimate.expected_close == "2026-06-07"
    assert estimate.latest_close == "2026-06-30"


def test_timeline_uses_a_causal_outside_date_extension_without_resetting_deal_age() -> None:
    announcement = replace(
        _ANNOUNCEMENT,
        timeline=DealTimelineEvidence(outside_date="2026-06-30"),
    )
    extension = replace(
        announcement,
        observed_at="2026-06-20T12:00:00+00:00",
        status=EventStatus.AMENDED,
        source_accession="extension",
        timeline=DealTimelineEvidence(outside_date="2026-12-31"),
    )

    estimate = DealTimeline().estimate(
        (announcement, extension),
        as_of=datetime(2026, 8, 1, 22, tzinfo=UTC),
    )

    assert estimate is not None
    assert estimate.announced_at == "2026-01-03T12:00:00+00:00"
    assert estimate.earliest_close == "2026-08-01"
    assert estimate.expected_close == "2026-10-16"
    assert estimate.latest_close == "2026-12-31"


def test_timeline_refuses_to_invent_a_close_horizon_without_causal_terms() -> None:
    event = replace(_ANNOUNCEMENT, timeline=None)

    estimate = DealTimeline().estimate(
        (event,),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
    )

    assert estimate is None

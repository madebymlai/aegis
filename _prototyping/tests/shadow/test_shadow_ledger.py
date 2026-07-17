from datetime import UTC, datetime

from _prototyping.merger.shadow import EventObservation, EventStatus, ShadowLedger


def test_replaying_the_same_source_observation_is_idempotent(tmp_path) -> None:
    observation = EventObservation(
        event_id="1141103:0000950103-24-017244",
        instrument_id="CCRN.XNAS",
        target_cik="1141103",
        ticker="CCRN",
        agreement_accession="0000950103-24-017244",
        agreement_date="2024-12-03",
        observed_at="2024-12-04T12:00:00+00:00",
        status=EventStatus.ANNOUNCED,
        offer_price=18.61,
        source_accession="0000950103-24-017244",
        source_url="https://example.test/ccrn-announcement",
        evidence="Aya agreed to acquire each share for $18.61 in cash.",
    )
    ledger = ShadowLedger(tmp_path)

    first = ledger.record((observation,))
    second = ledger.record((observation,))
    replay = ledger.events(as_of=datetime(2024, 12, 5, tzinfo=UTC))

    assert first.added == 1
    assert second.added == 0
    assert replay == (observation,)


def test_reducing_states_never_applies_one_agreements_terminal_to_another(tmp_path) -> None:
    old_announcement = EventObservation(
        event_id="1024725:old-agreement",
        instrument_id="HEES.XNAS",
        target_cik="1024725",
        ticker="HEES",
        agreement_accession="old-agreement",
        agreement_date="2025-01-13",
        observed_at="2025-01-14T12:00:00+00:00",
        status=EventStatus.ANNOUNCED,
        offer_price=92.00,
        source_accession="old-announcement",
        source_url="https://example.test/hees-old-announcement",
        evidence="United Rentals agreed to acquire HEES for $92.00 in cash.",
    )
    old_replacement = EventObservation(
        event_id="1024725:old-agreement",
        instrument_id="HEES.XNAS",
        target_cik="1024725",
        ticker="HEES",
        agreement_accession="old-agreement",
        agreement_date="2025-01-13",
        observed_at="2025-02-18T12:00:00+00:00",
        status=EventStatus.REPLACED,
        offer_price=92.00,
        source_accession="replacement-filing",
        source_url="https://example.test/hees-replacement",
        evidence="The old agreement was terminated when HEES signed with Herc.",
    )
    new_announcement = EventObservation(
        event_id="1024725:new-agreement",
        instrument_id="HEES.XNAS",
        target_cik="1024725",
        ticker="HEES",
        agreement_accession="new-agreement",
        agreement_date="2025-02-17",
        observed_at="2025-02-18T12:00:00+00:00",
        status=EventStatus.ANNOUNCED,
        offer_price=100.00,
        source_accession="replacement-filing",
        source_url="https://example.test/hees-replacement",
        evidence="Herc signed a different agreement for HEES.",
    )
    ledger = ShadowLedger(tmp_path)
    ledger.record((old_announcement, old_replacement, new_announcement))

    states = ledger.states(as_of=datetime(2025, 2, 19, tzinfo=UTC))

    assert states[0].event_id == "1024725:new-agreement"
    assert states[0].status is EventStatus.ANNOUNCED
    assert states[1].event_id == "1024725:old-agreement"
    assert states[1].status is EventStatus.REPLACED


def test_qualification_remains_closed_below_resolution_and_break_thresholds(tmp_path) -> None:
    announcement = EventObservation(
        event_id="1141103:agreement",
        instrument_id="CCRN.XNAS",
        target_cik="1141103",
        ticker="CCRN",
        agreement_accession="agreement",
        agreement_date="2024-12-03",
        observed_at="2024-12-04T12:00:00+00:00",
        status=EventStatus.ANNOUNCED,
        offer_price=18.61,
        source_accession="announcement",
        source_url="https://example.test/announcement",
        evidence="Cash merger announced.",
    )
    termination = EventObservation(
        event_id="1141103:agreement",
        instrument_id="CCRN.XNAS",
        target_cik="1141103",
        ticker="CCRN",
        agreement_accession="agreement",
        agreement_date="2024-12-03",
        observed_at="2025-12-04T12:00:00+00:00",
        status=EventStatus.TERMINATED,
        offer_price=18.61,
        source_accession="termination",
        source_url="https://example.test/termination",
        evidence="The identified merger agreement was terminated.",
    )
    ledger = ShadowLedger(tmp_path)
    ledger.record((announcement, termination))

    qualification = ledger.qualification(as_of=datetime(2025, 12, 5, tzinfo=UTC))

    assert qualification.resolved_events == 1
    assert qualification.adverse_resolutions == 1
    assert qualification.minimum_resolved_events == 100
    assert qualification.minimum_adverse_resolutions == 10
    assert qualification.ready_for_alpha_evaluation is False

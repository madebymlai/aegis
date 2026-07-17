from dataclasses import replace
from datetime import UTC, date, datetime

from _prototyping.merger.shadow import (
    CashMergerShadow,
    EventObservation,
    EventStatus,
    MarketMark,
    MarketMarkBatch,
    SourceRefresh,
)

_EVENT = EventObservation(
    event_id="1:announcement",
    target_cik="1",
    ticker="D01",
    agreement_accession="announcement",
    agreement_date="2026-01-02",
    observed_at="2026-01-03T12:00:00+00:00",
    status=EventStatus.ANNOUNCED,
    offer_price=10.20,
    source_accession="announcement",
    source_url="https://example.test/announcement",
    evidence="Each share converts into $10.20 in cash.",
)
_MARK = MarketMark(
    ticker="D01",
    observed_at="2026-02-02T21:00:00+00:00",
    close=10.00,
    preannouncement_close=9.00,
    market_close=100.00,
    announcement_market_close=100.00,
    beta=0.00,
    median_dollar_volume=5_000_000.00,
    annual_cash_rate=0.00,
)


class _Source:
    def refresh(self, *, start, end, active_events) -> SourceRefresh:
        return SourceRefresh(observations=(_EVENT,), reviews=())


class _Marks:
    def load(self, events, *, as_of) -> MarketMarkBatch:
        return MarketMarkBatch(marks=(_MARK,), unavailable=())


class _ResolvingSource:
    def __init__(self) -> None:
        self._refreshes = 0

    def refresh(self, *, start, end, active_events) -> SourceRefresh:
        self._refreshes += 1
        if self._refreshes == 1:
            return SourceRefresh(
                observations=tuple(
                    replace(
                        _EVENT,
                        event_id=f"{number}:announcement",
                        target_cik=str(number),
                        ticker=f"D{number:02d}",
                    )
                    for number in range(1, 11)
                ),
                reviews=(),
            )
        return SourceRefresh(
            observations=(
                replace(
                    _EVENT,
                    event_id="1:announcement",
                    observed_at="2026-02-03T12:00:00+00:00",
                    status=EventStatus.COMPLETED,
                    source_accession="completion",
                ),
            ),
            reviews=(),
        )


class _DiversifiedMarks:
    def load(self, events, *, as_of) -> MarketMarkBatch:
        return MarketMarkBatch(
            marks=tuple(replace(_MARK, ticker=f"D{number:02d}") for number in range(1, 11)),
            unavailable=(),
        )


def test_shadow_run_records_causal_evidence_without_promoting_the_strategy(tmp_path) -> None:
    shadow = CashMergerShadow(tmp_path)

    evidence = shadow.run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 2),
        end=date(2026, 2, 2),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    assert evidence.recorded_observations == 1
    assert evidence.decision_formed is True
    assert evidence.decision.positions == ()
    assert evidence.decision.cash_reserve == 5_000.00
    assert evidence.market_unavailable == 0
    assert evidence.qualification.ready_for_alpha_evaluation is False
    assert evidence.evidence_path.exists()


def test_refresh_window_resumes_after_the_latest_completed_source_day(tmp_path) -> None:
    shadow = CashMergerShadow(tmp_path)
    shadow.run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 2),
        end=date(2026, 2, 2),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    next_start = shadow.next_refresh_start(end=date(2026, 2, 4))

    assert next_start == date(2026, 2, 3)


def test_second_refresh_in_the_same_month_reuses_the_frozen_decision(tmp_path) -> None:
    shadow = CashMergerShadow(tmp_path)
    shadow.run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 2),
        end=date(2026, 2, 2),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    replay = shadow.run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 3),
        end=date(2026, 2, 3),
        as_of=datetime(2026, 2, 3, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    assert replay.decision_formed is False
    assert replay.decision.as_of == "2026-02-02T22:00:00+00:00"


def test_terminal_filing_emits_an_exit_without_reconstituting_the_monthly_book(
    tmp_path,
) -> None:
    source = _ResolvingSource()
    shadow = CashMergerShadow(tmp_path)
    first = shadow.run(
        source=source,
        marks=_DiversifiedMarks(),
        start=date(2026, 2, 2),
        end=date(2026, 2, 2),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    resolved = shadow.run(
        source=source,
        marks=_DiversifiedMarks(),
        start=date(2026, 2, 3),
        end=date(2026, 2, 3),
        as_of=datetime(2026, 2, 3, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    assert len(first.decision.positions) == 10
    assert resolved.decision_formed is False
    assert resolved.terminal_exit_event_ids == ("1:announcement",)

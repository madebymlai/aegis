import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from _prototyping.merger.shadow import (
    CashMergerSelector,
    CashMergerShadow,
    CloseGuidance,
    CompletionCase,
    CompletionForecast,
    DealTimelineEvidence,
    EventObservation,
    EventStatus,
    MarketMark,
    MarketMarkBatch,
    SelectionEngineIdentity,
    ShadowEvidenceError,
    SourceRefresh,
)

_EVENT = EventObservation(
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
    evidence="Each share converts into $10.20 in cash.",
    timeline=DealTimelineEvidence(
        guidance=CloseGuidance("2026-03-01", "2026-03-01"),
    ),
)
_MARK = MarketMark(
    instrument_id="D01.XNYS",
    ticker="D01",
    observed_at="2026-02-02T21:00:00+00:00",
    close=10.00,
    preannouncement_close=9.00,
    market_close=100.00,
    announcement_market_close=100.00,
    beta=0.00,
    median_dollar_volume=5_000_000.00,
    annual_cash_rate=0.00,
    preannouncement_closes=(9.00, 9.00, 9.00),
)


class _RejectingEngine:
    identity = SelectionEngineIdentity(
        engine_id="rejecting-test-model",
        model_artifact_id="rejecting-test-model-v1",
        training_cutoff="2025-12-31",
    )

    def forecast(
        self,
        cases: tuple[CompletionCase, ...],
    ) -> tuple[CompletionForecast, ...]:
        return tuple(
            CompletionForecast(
                event_id=case.event_id,
                feature_timestamp="2026-02-03T21:00:00+00:00",
                model_probability=0.50,
                lower_probability=0.40,
                selected=False,
                rank_score=0.0,
            )
            for case in cases
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
                        instrument_id=f"D{number:02d}.XNYS",
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
            marks=tuple(
                replace(
                    _MARK,
                    instrument_id=f"D{number:02d}.XNYS",
                    ticker=f"D{number:02d}",
                )
                for number in range(1, 11)
            ),
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
    assert evidence.selection_formed is True
    assert evidence.selection.engine.engine_id == "market-implied-q70"
    assert evidence.selection.assessments[0].market_probability == pytest.approx(
        0.8333333333333333
    )
    assert evidence.selection.assessments[0].probability_edge == 0.0
    assert evidence.selection.decision.positions == ()
    assert evidence.selection.decision.cash_reserve == 5_000.00
    assert evidence.market_unavailable == 0
    assert evidence.qualification.ready_for_alpha_evaluation is False
    assert evidence.evidence_path.exists()


def test_shadow_run_persists_the_current_fx_cost_contract(tmp_path) -> None:
    evidence = CashMergerShadow(tmp_path).run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 2),
        end=date(2026, 2, 2),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    payload = json.loads(evidence.evidence_path.read_text())
    assert payload["schema_version"] == 7
    assert payload["selection"]["decision"]["estimated_fx_conversion"] == 0.0


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

    next_start = shadow.next_refresh_start(
        end=date(2026, 2, 4),
        bootstrap_start=date(2025, 7, 1),
    )

    assert next_start == date(2026, 2, 3)


def test_empty_refresh_window_starts_at_explicit_bootstrap_date(tmp_path) -> None:
    next_start = CashMergerShadow(tmp_path).next_refresh_start(
        end=date(2026, 2, 4),
        bootstrap_start=date(2025, 7, 1),
    )

    assert next_start == date(2025, 7, 1)


def test_bootstrap_start_cannot_follow_refresh_end(tmp_path) -> None:
    with pytest.raises(ValueError, match="bootstrap start exceeds refresh end"):
        CashMergerShadow(tmp_path).next_refresh_start(
            end=date(2026, 2, 4),
            bootstrap_start=date(2026, 2, 5),
        )


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

    assert replay.selection_formed is False
    assert replay.selection.decision.as_of == "2026-02-02T22:00:00+00:00"


def test_different_engine_forms_independent_evidence_in_the_same_month(tmp_path) -> None:
    CashMergerShadow(tmp_path).run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 2),
        end=date(2026, 2, 2),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )
    challenger = CashMergerShadow(
        tmp_path,
        selector=CashMergerSelector(_RejectingEngine()),
    )

    evidence = challenger.run(
        source=_Source(),
        marks=_Marks(),
        start=date(2026, 2, 3),
        end=date(2026, 2, 3),
        as_of=datetime(2026, 2, 3, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    assert evidence.selection_formed is True
    assert evidence.selection.engine.engine_id == "rejecting-test-model"
    assert evidence.selection.decision_engine_id == "market-implied-q70"
    assert evidence.selection.decision.as_of == "2026-02-03T22:00:00+00:00"


def test_current_schema_evidence_cannot_fail_open(tmp_path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "malformed.json").write_text(
        json.dumps(
            {
                "schema_version": 7,
                "selection_formed": True,
                "selection": {},
            }
        )
    )

    with pytest.raises(ShadowEvidenceError, match="malformed shadow evidence"):
        CashMergerShadow(tmp_path).run(
            source=_Source(),
            marks=_Marks(),
            start=date(2026, 2, 2),
            end=date(2026, 2, 2),
            as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
            capital=5_000.00,
        )


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

    assert len(first.selection.decision.positions) == 10
    assert resolved.selection_formed is False
    assert resolved.terminal_exit_event_ids == ("1:announcement",)

"""Behavior checks for market-anchored, swappable merger selection."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from _prototyping.merger.shadow import (
    CashMergerSelector,
    CloseGuidance,
    CompletionCase,
    CompletionForecast,
    CompletionSelectionEngine,
    DealTimelineEvidence,
    EngineCausalityError,
    EventObservation,
    EventStatus,
    MarketMark,
    SelectionAuthority,
    SelectionEngineIdentity,
    SelectionExclusionReason,
)

_AS_OF = datetime(2026, 2, 2, 22, tzinfo=UTC)


def _event(number: int) -> EventObservation:
    ticker = f"D{number:02d}"
    accession = f"announcement-{number:02d}"
    return EventObservation(
        event_id=f"{number}:{accession}",
        instrument_id=f"{ticker}.XNYS",
        target_cik=str(number),
        ticker=ticker,
        agreement_accession=accession,
        agreement_date="2026-01-02",
        observed_at="2026-01-03T12:00:00+00:00",
        status=EventStatus.ANNOUNCED,
        offer_price=10.20,
        source_accession=accession,
        source_url=f"https://example.test/{ticker}",
        evidence="Each share converts into $10.20 in cash.",
        timeline=DealTimelineEvidence(
            guidance=CloseGuidance("2026-03-01", "2026-03-01"),
        ),
    )


def _mark(number: int, close: float = 10.00) -> MarketMark:
    return MarketMark(
        instrument_id=f"D{number:02d}.XNYS",
        ticker=f"D{number:02d}",
        observed_at="2026-02-02T21:00:00+00:00",
        close=close,
        preannouncement_close=9.00,
        market_close=100.00,
        announcement_market_close=100.00,
        beta=0.00,
        median_dollar_volume=5_000_000.00,
        annual_cash_rate=0.00,
        preannouncement_closes=(9.00, 9.00, 9.00),
    )


_TEN_EVENTS = tuple(_event(number) for number in range(1, 11))
_TEN_MARKS = tuple(_mark(number) for number in range(1, 11))
_ELEVEN_EVENTS = (*_TEN_EVENTS, _event(11))
_ELEVEN_MARKS = (*_TEN_MARKS, _mark(11, 9.50))
_EXPECTED_TICKERS = (
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "D07",
    "D08",
    "D09",
    "D10",
)


class _IndependentCompletionEngine(CompletionSelectionEngine):
    def __init__(
        self,
        *,
        training_cutoff: str = "2025-12-31",
        selected: bool = False,
    ) -> None:
        self.identity = SelectionEngineIdentity(
            engine_id="independent-test-model",
            model_artifact_id="independent-test-model-v1",
            training_cutoff=training_cutoff,
        )
        self._selected = selected

    def forecast(
        self,
        cases: tuple[CompletionCase, ...],
    ) -> tuple[CompletionForecast, ...]:
        return tuple(
            CompletionForecast(
                event_id=case.event_id,
                feature_timestamp="2026-02-02T21:00:00+00:00",
                model_probability=0.90,
                lower_probability=0.85,
                selected=self._selected,
                rank_score=0.90 - case.market_probability,
            )
            for case in cases
        )


def test_market_baseline_records_the_probability_and_payoff_audit() -> None:
    selection = CashMergerSelector().select(
        (_event(1),),
        (_mark(1),),
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assessment = selection.assessments[0]
    assert selection.engine.engine_id == "market-implied-q70"
    assert selection.decision_engine_id == "market-implied-q70"
    assert assessment.as_of == "2026-02-02T22:00:00+00:00"
    assert assessment.market_probability == pytest.approx(0.8333333333333333)
    assert assessment.model_probability == pytest.approx(0.8333333333333333)
    assert assessment.probability_edge == 0.0
    assert assessment.market_gross_expected_payoff == pytest.approx(0.0, abs=1e-15)
    assert assessment.model_gross_expected_payoff == pytest.approx(0.0, abs=1e-15)


def test_market_baseline_preserves_whole_share_cash_and_cost_accounting() -> None:
    selection = CashMergerSelector().select(
        _ELEVEN_EVENTS,
        _ELEVEN_MARKS,
        as_of=_AS_OF,
        capital=5_000.00,
    )

    decision = selection.decision
    assert len(selection.assessments) == 11
    assert len(decision.positions) == 10
    assert decision.positions[0].shares == 49
    assert decision.positions[0].target_weight == 0.098
    assert tuple(sorted(position.ticker for position in decision.positions)) == (
        _EXPECTED_TICKERS
    )
    assert decision.estimated_base_commission == 3.50
    assert decision.estimated_slippage == 2.45
    assert decision.estimated_fx_conversion == 1.47
    assert decision.cash_reserve == 92.58


def _low_price_decision():
    events = tuple(
        replace(_event(number), offer_price=2.20) for number in range(1, 11)
    )
    marks = tuple(
        replace(
            _mark(number, 2.00),
            preannouncement_close=1.50,
            preannouncement_closes=(1.50, 1.50, 1.50),
        )
        for number in range(1, 11)
    )

    return CashMergerSelector().select(
        events,
        marks,
        as_of=_AS_OF,
        capital=5_000.00,
    ).decision


def test_cost_aware_sizing_reserves_tiered_commission_above_the_minimum() -> None:
    assert _low_price_decision().positions[0].shares == 199


def test_tiered_base_commission_increases_with_large_share_counts() -> None:
    assert _low_price_decision().estimated_base_commission == 6.97


def test_unqualified_challenger_is_audited_while_market_baseline_controls_trades() -> None:
    selection = CashMergerSelector(_IndependentCompletionEngine()).select(
        _TEN_EVENTS,
        _TEN_MARKS,
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assessment = selection.assessments[0]
    assert selection.engine.model_artifact_id == "independent-test-model-v1"
    assert selection.engine.training_cutoff == "2025-12-31"
    assert selection.decision_engine_id == "market-implied-q70"
    assert assessment.market_probability == pytest.approx(0.8333333333333333)
    assert assessment.model_probability == 0.90
    assert assessment.feature_timestamp == "2026-02-02T21:00:00+00:00"
    assert assessment.lower_probability == 0.85
    assert assessment.probability_edge == pytest.approx(0.06666666666666667)
    assert assessment.selected is False
    assert len(selection.decision.positions) == 10


def test_qualified_challenger_can_control_the_decision_without_changing_sizing() -> None:
    selector = CashMergerSelector(
        _IndependentCompletionEngine(),
        authority=SelectionAuthority.QUALIFIED_CHALLENGER,
    )

    selection = selector.select(
        _TEN_EVENTS,
        _TEN_MARKS,
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assert selection.decision_engine_id == "independent-test-model"
    assert selection.decision.positions == ()
    assert selection.decision.cash_reserve == 5_000.00


def test_completion_engine_cannot_use_a_future_training_cohort() -> None:
    selector = CashMergerSelector(
        _IndependentCompletionEngine(training_cutoff="2026-12-31")
    )

    with pytest.raises(
        EngineCausalityError,
        match="training_cutoff exceeds selection as_of",
    ):
        selector.select(
            _TEN_EVENTS,
            _TEN_MARKS,
            as_of=_AS_OF,
            capital=5_000.00,
        )


def test_selector_excludes_a_deal_without_positive_discounted_spread() -> None:
    selection = CashMergerSelector().select(
        (_event(1),),
        (_mark(1, 10.30),),
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assert selection.assessments == ()
    assert selection.exclusions[0].event_id == "1:announcement-01"
    assert (
        selection.exclusions[0].reason
        is SelectionExclusionReason.NO_POSITIVE_DISCOUNTED_SPREAD
    )


def test_selector_excludes_an_unidentified_break_value_instead_of_assigning_zero() -> None:
    mark = replace(
        _mark(1),
        preannouncement_close=10.10,
        preannouncement_closes=(10.05, 10.10, 10.15),
    )

    selection = CashMergerSelector().select(
        (_event(1),),
        (mark,),
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assert selection.assessments == ()
    assert (
        selection.exclusions[0].reason
        is SelectionExclusionReason.BREAK_VALUE_UNIDENTIFIED
    )


def test_selector_uses_causal_close_guidance_instead_of_a_fixed_deal_horizon() -> None:
    event = _event(1)
    mark = _mark(1)
    event = replace(
        event,
        timeline=DealTimelineEvidence(
            guidance=CloseGuidance("2026-02-12", "2026-02-12"),
        ),
    )
    mark = replace(mark, annual_cash_rate=0.10)

    selection = CashMergerSelector().select(
        (event,),
        (mark,),
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assessment = selection.assessments[0]
    assert assessment.expected_close == "2026-02-12"
    assert assessment.discounted_offer == pytest.approx(10.1721300137)


def test_selector_audits_break_uncertainty_and_uses_its_lower_probability_bound() -> None:
    mark = replace(
        _mark(1),
        preannouncement_closes=(8.00, 9.00, 10.00),
    )

    selection = CashMergerSelector().select(
        (_event(1),),
        (mark,),
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assessment = selection.assessments[0]
    assert assessment.break_value_lower == 8.50
    assert assessment.break_value_central == 9.00
    assert assessment.break_value_upper == 9.50
    assert assessment.market_probability_lower == pytest.approx(0.7142857142857143)
    assert assessment.market_probability == pytest.approx(0.8333333333333333)
    assert assessment.market_probability_upper == pytest.approx(0.8823529411764706)
    assert assessment.selected is True


def test_selector_excludes_a_deal_when_no_causal_close_range_exists() -> None:
    event = replace(_event(1), timeline=None)

    selection = CashMergerSelector().select(
        (event,),
        (_mark(1),),
        as_of=_AS_OF,
        capital=5_000.00,
    )

    assert selection.assessments == ()
    assert selection.exclusions[0].reason is SelectionExclusionReason.TIMELINE_UNAVAILABLE

from datetime import UTC, datetime

from _prototyping.merger.shadow import (
    EventObservation,
    EventStatus,
    FrozenQ70Policy,
    MarketMark,
)


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
    )


def test_q70_decision_excludes_low_probability_and_preserves_whole_share_cash() -> None:
    events = tuple(_event(number) for number in range(1, 12))
    marks = (*(_mark(number) for number in range(1, 11)), _mark(11, 9.50))
    policy = FrozenQ70Policy()

    decision = policy.decide(
        events,
        marks,
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
        capital=5_000.00,
    )

    assert len(decision.positions) == 10
    assert decision.positions[0].shares == 49
    assert decision.positions[0].target_weight == 0.098
    assert tuple(sorted(position.ticker for position in decision.positions)) == (
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
    assert decision.estimated_commissions == 3.50
    assert decision.estimated_slippage == 2.45
    assert decision.cash_reserve == 94.05

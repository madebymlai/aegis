"""Behavior checks for independent merger-break downside estimation."""

from _prototyping.merger.shadow import BreakValueModel, MarketMark


def test_break_value_is_a_market_adjusted_range_not_one_preannouncement_price() -> None:
    mark = MarketMark(
        instrument_id="D01.XNYS",
        ticker="D01",
        observed_at="2026-02-02T21:00:00+00:00",
        close=10.00,
        preannouncement_close=9.00,
        market_close=121.00,
        announcement_market_close=100.00,
        beta=0.50,
        median_dollar_volume=5_000_000.00,
        annual_cash_rate=0.00,
        preannouncement_closes=(8.00, 9.00, 10.00),
    )

    estimate = BreakValueModel().estimate(mark)

    assert estimate.lower == 9.35
    assert estimate.central == 9.90
    assert estimate.upper == 10.45


def test_break_value_uses_the_available_anchor_when_history_is_sparse() -> None:
    mark = MarketMark(
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
    )

    estimate = BreakValueModel().estimate(mark)

    assert estimate.lower == 9.00
    assert estimate.central == 9.00
    assert estimate.upper == 9.00

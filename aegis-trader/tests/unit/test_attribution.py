"""Unit tests for per-sleeve P&L attribution — pure domain, zero Nautilus.

Per-sleeve attribution is derived from weights × book returns (not a second
ledger).  The sleeve P&L at time t is:

    Σ (weight_{i,t-1} × return_{i,t})

where return_{i,t} = close_{i,t} / close_{i,t-1} - 1.  Sleeve attribution
must sum to the total book P&L.
"""

from __future__ import annotations

import pandas as pd
import pytest

from aegis_trader.domain.attribution import compute_sleeve_attribution
from aegis_trader.domain.types import SleeveName


_DEFAULT_DATES = [
    "2025-06-01", "2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05",
]


def _make_weight_df(
    figi_to_weights: dict[str, list[float]],
    index: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """Build a multi-row target-weight DataFrame.

    When *index* is None the index is auto-sized to match the length of the
    first value list.
    """
    if index is None:
        first_len = len(next(iter(figi_to_weights.values())))
        index = pd.DatetimeIndex(_DEFAULT_DATES[:first_len], name="timestamp")
    df = pd.DataFrame(figi_to_weights, index=index)
    df.columns.name = "figi"
    return df


def _make_close_df(
    figi_to_prices: dict[str, list[float]],
    index: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """Build a multi-row close-price DataFrame.

    When *index* is None the index is auto-sized to match the length of the
    first value list.
    """
    if index is None:
        first_len = len(next(iter(figi_to_prices.values())))
        index = pd.DatetimeIndex(_DEFAULT_DATES[:first_len], name="timestamp")
    df = pd.DataFrame(figi_to_prices, index=index)
    df.columns.name = "figi"
    return df


class TestSleeveAttribution:
    """Per-sleeve P&L attribution — weights × returns."""

    def test_single_sleeve_single_figi_positive_return(self):
        """One sleeve, one FIGI, positive return → P&L = weight × return."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        # 5 days, weight constant at 0.5
        weights = _make_weight_df({figi: [0.5, 0.5, 0.5, 0.5, 0.5]})
        # Prices: 100, 101, 102, 103, 104 → ~1% daily return
        closes = _make_close_df({figi: [100.0, 101.0, 102.0, 103.0, 104.0]})
        # NAV constant at 100,000
        nav_series = pd.Series([100_000.0] * 5, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        assert sleeve_name in result
        pnl = result[sleeve_name]

        # Day 1: weight 0.5, return = (101/100 - 1) = 0.01
        # Day 2: weight 0.5, return = (102/101 - 1) = ~0.0099
        # Day 3: weight 0.5, return = (103/102 - 1) = ~0.0098
        # Day 4: weight 0.5, return = (104/103 - 1) = ~0.0097
        # P&L = Σ 0.5 × return_i × 100000
        expected = 100_000.0 * 0.5 * (
            (101.0 / 100.0 - 1) + (102.0 / 101.0 - 1) + (103.0 / 102.0 - 1) + (104.0 / 103.0 - 1)
        )
        assert pnl == pytest.approx(expected, rel=1e-9)

    def test_negative_return_produces_negative_pnl(self):
        """Falling prices → negative P&L."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        weights = _make_weight_df({figi: [0.5, 0.5, 0.5]})
        closes = _make_close_df(
            {figi: [100.0, 98.0, 96.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        assert result[sleeve_name] < 0

    def test_weight_changes_correctly_accounted(self):
        """When the target weight changes, the new weight applies to the next return."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        # Weight goes from 0.5 → 1.0 → 0.0 → 0.5
        weights = _make_weight_df(
            {figi: [0.5, 1.0, 0.0, 0.5, 0.5]},
        )
        closes = _make_close_df({figi: [100.0, 101.0, 102.0, 103.0, 104.0]})
        nav_series = pd.Series([100_000.0] * 5, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        # Period 1: w0=0.5, ret1 = 101/100-1 = 0.01
        # Period 2: w1=1.0, ret2 = 102/101-1 ≈ 0.0099
        # Period 3: w2=0.0, ret3 = 103/102-1 ≈ 0.0098
        # Period 4: w3=0.5, ret4 = 104/103-1 ≈ 0.0097
        expected = 100_000.0 * (
            0.5 * (101.0 / 100.0 - 1)
            + 1.0 * (102.0 / 101.0 - 1)
            + 0.0 * (103.0 / 102.0 - 1)
            + 0.5 * (104.0 / 103.0 - 1)
        )
        assert result[sleeve_name] == pytest.approx(expected, rel=1e-9)

    def test_zero_weight_produces_zero_contribution(self):
        """Zero weights contribute nothing to P&L."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        weights = _make_weight_df({figi: [0.0, 0.0, 0.0]})
        closes = _make_close_df(
            {figi: [100.0, 200.0, 300.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        assert result[sleeve_name] == pytest.approx(0.0, abs=1e-12)

    def test_short_weight_produces_inverse_pnl(self):
        """A negative weight reverses the return direction."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        weights = _make_weight_df({figi: [-0.5, -0.5, -0.5]})
        closes = _make_close_df(
            {figi: [100.0, 110.0, 120.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        # Rising prices with short weight → negative P&L
        assert result[sleeve_name] < 0

    def test_short_weight_with_falling_prices_produces_positive_pnl(self):
        """Short + falling prices → positive P&L."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        weights = _make_weight_df({figi: [-0.5, -0.5, -0.5]})
        closes = _make_close_df(
            {figi: [100.0, 90.0, 80.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        assert result[sleeve_name] > 0

    def test_multiple_figis_summed(self):
        """Multiple FIGIs in a sleeve — P&L is summed across them."""
        sleeve_name = SleeveName("trend")
        weights = _make_weight_df({
            "FIGI_A": [0.3, 0.3, 0.3],
            "FIGI_B": [0.2, 0.2, 0.2],
        })
        closes = _make_close_df(
            {
                "FIGI_A": [100.0, 110.0, 120.0],
                "FIGI_B": [50.0, 55.0, 60.0],
            },
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        # FIGI_A: 0.3 * (0.1 + 0.0909)  * 100000
        # FIGI_B: 0.2 * (0.1 + 0.0909) * 100000
        expected = 100_000.0 * (
            0.3 * ((110.0 / 100.0 - 1) + (120.0 / 110.0 - 1))
            + 0.2 * ((55.0 / 50.0 - 1) + (60.0 / 55.0 - 1))
        )
        assert result[sleeve_name] == pytest.approx(expected, rel=1e-9)

    def test_nav_changes_across_periods(self):
        """NAV changes over time — each period uses its period's NAV."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        weights = _make_weight_df({figi: [0.5, 0.5, 0.5]})
        closes = _make_close_df(
            {figi: [100.0, 110.0, 120.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0, 105_000.0, 110_000.0], index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        # Period 1: NAV=100_000, w=0.5, ret=0.1 → 5_000
        # Period 2: NAV=105_000, w=0.5, ret=0.0909 → 4_772.73
        expected = (
            100_000.0 * 0.5 * (110.0 / 100.0 - 1)
            + 105_000.0 * 0.5 * (120.0 / 110.0 - 1)
        )
        assert result[sleeve_name] == pytest.approx(expected, rel=1e-3)

    def test_single_period_no_returns(self):
        """Only one time point → no returns to compute → zero P&L."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        weights = _make_weight_df(
            {figi: [0.5]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        closes = _make_close_df(
            {figi: [100.0]},
            index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0], index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        assert result[sleeve_name] == pytest.approx(0.0, abs=1e-12)

    def test_attribution_sums_to_book_pnl(self):
        """Per-sleeve attribution must sum to total book P&L."""
        # Two sleeves with different instruments
        trend_name = SleeveName("trend")
        carry_name = SleeveName("carry")

        trend_weights = _make_weight_df({
            "FIGI_A": [0.4, 0.4, 0.4],
            "FIGI_B": [0.1, 0.1, 0.1],
        })
        carry_weights = _make_weight_df({
            "FIGI_A": [-0.2, -0.2, -0.2],
            "FIGI_C": [0.3, 0.3, 0.3],
        })

        closes = _make_close_df(
            {
                "FIGI_A": [100.0, 105.0, 110.0],
                "FIGI_B": [50.0, 52.0, 48.0],
                "FIGI_C": [200.0, 210.0, 215.0],
            },
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={trend_name: trend_weights, carry_name: carry_weights},
            closes=closes,
            nav_series=nav_series,
        )

        trend_pnl = result[trend_name]
        carry_pnl = result[carry_name]

        # Compute the book P&L by netting weights and calculating directly
        net_weights = _make_weight_df({
            "FIGI_A": [0.2, 0.2, 0.2],   # 0.4 - 0.2
            "FIGI_B": [0.1, 0.1, 0.1],   # 0.1
            "FIGI_C": [0.3, 0.3, 0.3],   # 0.3
        })

        book_result = compute_sleeve_attribution(
            sleeve_targets={SleeveName("book"): net_weights},
            closes=closes,
            nav_series=nav_series,
        )
        book_pnl = book_result[SleeveName("book")]

        assert trend_pnl + carry_pnl == pytest.approx(book_pnl, rel=1e-9), (
            f"trend={trend_pnl:.4f} + carry={carry_pnl:.4f} = {trend_pnl + carry_pnl:.4f} "
            f"≠ book={book_pnl:.4f}"
        )

    def test_missing_figi_in_closes(self):
        """FIGI present in weights but missing from close prices → zero contribution."""
        sleeve_name = SleeveName("trend")
        weights = _make_weight_df({
            "FIGI_A": [0.5, 0.5, 0.5],
            "MISSING": [0.5, 0.5, 0.5],
        })
        closes = _make_close_df(
            {"FIGI_A": [100.0, 110.0, 120.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        # Only FIGI_A contributes; MISSING is ignored
        expected = 100_000.0 * (
            0.5 * (110.0 / 100.0 - 1) + 0.5 * (120.0 / 110.0 - 1)
        )
        assert result[sleeve_name] == pytest.approx(expected, rel=1e-9)

    def test_empty_sleeves_returns_empty_dict(self):
        """No sleeves → empty result."""
        closes = _make_close_df(
            {"FIGI_A": [100.0, 110.0]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02"], name="timestamp"),
        )
        nav_series = pd.Series([100_000.0] * 2, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={},
            closes=closes,
            nav_series=nav_series,
        )

        assert result == {}

    def test_index_mismatch_aligns_on_common(self):
        """Weights and closes with different index lengths → aligned on common dates."""
        sleeve_name = SleeveName("trend")
        figi = "FIGI_A"
        # Weights have 5 days, closes have only 3 overlapping
        weights = _make_weight_df({figi: [0.5, 0.5, 0.5, 0.5, 0.5]})
        closes = _make_close_df(
            {figi: [100.0, 101.0, 102.0]},
            index=pd.DatetimeIndex(
                ["2025-06-02", "2025-06-03", "2025-06-04"], name="timestamp"
            ),
        )
        nav_series = pd.Series([100_000.0] * 3, index=closes.index)

        result = compute_sleeve_attribution(
            sleeve_targets={sleeve_name: weights},
            closes=closes,
            nav_series=nav_series,
        )

        # Only 2 periods with returns: Jun 3-4
        expected = 100_000.0 * (
            0.5 * (101.0 / 100.0 - 1) + 0.5 * (102.0 / 101.0 - 1)
        )
        assert result[sleeve_name] == pytest.approx(expected, rel=1e-9)

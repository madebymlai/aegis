from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _prototyping.eu_variance_premium.model import (
    NeweyWestMeanTest,
    StructuralBreakResult,
)
from _prototyping.global_variance_premium import cross_market as cm
from _prototyping.global_variance_premium import market_history as mh
from _prototyping.global_variance_premium.universe import MarketSpec

_BREAK_DATE = "2012-08-01"


def _break_result(
    *, pre_mean: float, post_mean: float, se: float
) -> StructuralBreakResult:
    pre = NeweyWestMeanTest(
        mean=pre_mean,
        standard_error=se,
        t_statistic=0.0,
        p_value=0.0,
        observations=100,
        lags=5,
    )
    post = NeweyWestMeanTest(
        mean=post_mean,
        standard_error=se,
        t_statistic=0.0,
        p_value=0.0,
        observations=100,
        lags=5,
    )
    difference = post_mean - pre_mean
    return StructuralBreakResult(
        break_date=_BREAK_DATE,
        pre=pre,
        post=post,
        difference=difference,
        difference_t_statistic=0.0,
        difference_p_value=0.0,
    )


def test_compare_break_changes_finds_no_difference_between_identical_changes() -> None:
    reference = _break_result(pre_mean=5.0, post_mean=3.0, se=0.1)
    other = _break_result(pre_mean=5.0, post_mean=3.0, se=0.1)

    comparison = cm.compare_break_changes(
        reference, other, reference_label="US", other_label="Other"
    )

    assert comparison.difference_of_changes == 0.0
    assert comparison.z_statistic == 0.0
    assert comparison.p_value == 1.0


def test_compare_break_changes_flags_a_clearly_different_change() -> None:
    reference = _break_result(pre_mean=5.0, post_mean=5.0, se=0.1)  # flat
    other = _break_result(pre_mean=5.0, post_mean=0.0, se=0.1)  # a 5-point drop

    comparison = cm.compare_break_changes(
        reference, other, reference_label="US", other_label="Other"
    )

    assert comparison.difference_of_changes == -5.0
    assert comparison.z_statistic == pytest.approx(-25.0)
    assert comparison.p_value < 1e-10


def test_probe_ticker_reports_available_with_the_series_date_range() -> None:
    index = pd.bdate_range("2020-01-01", periods=3)
    closes = pd.DataFrame({"Close": [10.0, 12.0, 11.0]}, index=index)

    result = mh.probe_ticker(
        "^FAKE",
        start="2020-01-01",
        end="2020-01-10",
        loader=lambda ticker, start, end: closes,
    )

    assert result.available is True
    assert result.observations == 3
    assert result.start == "2020-01-01"
    assert result.end == "2020-01-03"


def test_probe_ticker_reports_the_failure_reason_when_the_loader_raises() -> None:
    def failing_loader(ticker: str, start: str, end: str) -> pd.DataFrame:
        raise ValueError("boom")

    result = mh.probe_ticker("^FAKE", loader=failing_loader)

    assert result.available is False
    assert "boom" in result.detail


def test_load_market_pairs_the_vol_level_with_the_equity_log_returns() -> None:
    index = pd.bdate_range("2020-01-01", periods=3)
    vol_closes = pd.DataFrame({"Close": [20.0, 22.0, 18.0]}, index=index)
    equity_closes = pd.DataFrame({"Close": [100.0, 110.0, 99.0]}, index=index)

    def fake_loader(ticker: str, start: str, end: str) -> pd.DataFrame:
        return vol_closes if ticker == "^FAKEVOL" else equity_closes

    spec = MarketSpec(
        label="Fakeland", vol_ticker="^FAKEVOL", equity_ticker="^FAKEEQ", note="test"
    )

    market = mh.load_market(
        spec,
        start="2020-01-01",
        end="2020-01-10",
        cache_dir=None,
        refresh=False,
        loader=fake_loader,
    )

    assert market.vol_level.tolist() == [20.0, 22.0, 18.0]
    np.testing.assert_allclose(
        market.equity_log_returns.to_numpy(),
        [0.09531017980432493, -0.10536051565782628],
    )

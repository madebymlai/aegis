from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _prototyping.eu_variance_premium import model as m
from _prototyping.eu_variance_premium import stoxx_history as sh
from _prototyping.eu_variance_premium import synthetic as syn
from _prototyping.eu_variance_premium import yahoo_history as yh


def test_forward_realized_variance_sums_the_correct_forward_window() -> None:
    index = pd.bdate_range("2020-01-01", periods=5)
    returns = pd.Series(np.sqrt([1.0, 2.0, 3.0, 4.0, 5.0]), index=index)

    forward = m.forward_realized_variance(returns, horizon=2)

    # value at t is the annualized sum of squared returns at t+1 and t+2, excluding t.
    assert forward.iloc[0] == pytest.approx(630.0)
    assert len(forward) == 3  # last two dates have no full forward window


def test_variance_gap_recovers_a_known_embedded_gap() -> None:
    market = syn.synthetic_market(
        days=3000,
        break_date="2015-01-05",
        pre_gap_vol_points=3.0,
        post_gap_vol_points=0.2,
    )

    gap = m.variance_gap(market.vstoxx_level, market.sx5e_log_returns)
    result = m.structural_break_test(
        gap["gap_vol_points"], market.break_date, lags=m.VSTOXX_HORIZON_TRADING_DAYS - 1
    )

    assert result.pre.mean == pytest.approx(3.0, abs=0.1)
    assert result.post.mean == pytest.approx(0.2, abs=0.1)


def test_variance_gap_rejects_series_with_too_little_overlap() -> None:
    short_index = pd.bdate_range("2020-01-01", periods=5)
    vstoxx = pd.Series(20.0, index=short_index)
    returns = pd.Series(0.001, index=short_index)

    with pytest.raises(m.InsufficientHistory):
        m.variance_gap(vstoxx, returns, horizon=21)


def test_newey_west_mean_test_matches_the_iid_standard_error_at_zero_lags() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    result = m.newey_west_mean_test(x, lags=0)

    # with no HAC lags, this must reduce to the textbook iid standard error of a mean.
    assert result.mean == pytest.approx(3.0)
    assert result.standard_error == pytest.approx(0.6324555320336759)


def test_structural_break_test_detects_a_known_mean_shift() -> None:
    rng = np.random.default_rng(1)
    index = pd.bdate_range("2010-01-04", periods=2000)
    values = np.concatenate([rng.normal(5.0, 1.0, 1000), rng.normal(1.0, 1.0, 1000)])
    series = pd.Series(values, index=index)
    break_date = index[1000].date().isoformat()

    result = m.structural_break_test(series, break_date, lags=5)

    assert result.pre.mean == pytest.approx(5.0, abs=0.2)
    assert result.post.mean == pytest.approx(1.0, abs=0.2)
    assert abs(result.difference_t_statistic) > 10.0  # a real 4-sigma-scale shift


def test_structural_break_test_rejects_a_break_date_outside_the_series() -> None:
    index = pd.bdate_range("2010-01-04", periods=100)
    series = pd.Series(0.0, index=index)

    with pytest.raises(m.InsufficientHistory):
        m.structural_break_test(series, "2030-01-01", lags=5)


def test_slow_trend_returns_do_not_look_ahead() -> None:
    rng = np.random.default_rng(2)
    index = pd.bdate_range("2015-01-01", periods=400)
    returns = pd.Series(rng.normal(0.0002, 0.01, 400), index=index)
    perturbed = returns.copy()
    perturbed.iloc[-1] += 0.5  # a large, obviously out-of-distribution future move

    original = m.slow_trend_returns(returns, lookback=252)
    changed = m.slow_trend_returns(perturbed, lookback=252)

    pd.testing.assert_series_equal(original.iloc[:-1], changed.iloc[:-1])


def test_slow_trend_returns_follows_the_sign_of_the_trailing_move() -> None:
    index = pd.bdate_range("2015-01-01", periods=400)
    returns = pd.Series(0.001, index=index)  # a steady uptrend throughout

    trend = m.slow_trend_returns(returns, lookback=252)

    assert (trend > 0.0).all()


def test_daily_short_vol_payoff_uses_yesterdays_implied_level_not_todays() -> None:
    index = pd.bdate_range("2020-01-01", periods=5)
    returns = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0], index=index)
    vstoxx = pd.Series([20.0, 20.0, 20.0, 90.0, 20.0], index=index)  # a one-day spike

    payoff = m.daily_short_vol_payoff(vstoxx, returns)

    # the spike on day 4 (index position 3) should only inflate day 5's payoff, not day 4's
    assert payoff.iloc[2] == pytest.approx(0.00015873015873015876)
    assert payoff.iloc[3] == pytest.approx(0.0032142857142857147)


def test_loss_state_overlap_flags_the_worst_short_vol_days() -> None:
    index = pd.bdate_range("2020-01-01", periods=100)
    short_vol = pd.Series(0.0, index=index)
    short_vol.iloc[:5] = -10.0  # five clearly-worst days
    trend = pd.Series(0.0, index=index)
    trend.iloc[:5] = -0.02  # trend also loses on exactly those days

    overlap = m.loss_state_overlap(short_vol, trend, worst_quantile=0.05)

    assert overlap.worst_days == 5
    assert overlap.trend_return_on_worst_days_mean == pytest.approx(-0.02)
    assert overlap.trend_share_positive_on_worst_days == 0.0


def test_load_sx5e_log_returns_computes_log_returns_from_close() -> None:
    index = pd.bdate_range("2020-01-01", periods=3)
    closes = pd.DataFrame({"Close": [100.0, 110.0, 99.0]}, index=index)

    loaded = yh.load_sx5e_log_returns(
        "2020-01-01", "2020-01-10", loader=lambda ticker, start, end: closes
    )

    np.testing.assert_allclose(
        loaded.series.to_numpy(), [0.09531017980432493, -0.10536051565782628]
    )


def test_load_sx5e_log_returns_rejects_an_implausible_single_day_move() -> None:
    index = pd.bdate_range("2020-01-01", periods=3)
    closes = pd.DataFrame({"Close": [100.0, 500.0, 501.0]}, index=index)

    with pytest.raises(yh.MarketDataError):
        yh.load_sx5e_log_returns(
            "2020-01-01", "2020-01-10", loader=lambda ticker, start, end: closes
        )


def test_load_sx5e_log_returns_uses_the_cache_on_a_second_call(tmp_path) -> None:
    index = pd.bdate_range("2020-01-01", periods=3)
    closes = pd.DataFrame({"Close": [100.0, 110.0, 99.0]}, index=index)
    calls = {"count": 0}

    def counting_loader(ticker: str, start: str, end: str) -> pd.DataFrame:
        calls["count"] += 1
        return closes

    first = yh.load_sx5e_log_returns(
        "2020-01-01", "2020-01-10", cache_dir=tmp_path, loader=counting_loader
    )
    second = yh.load_sx5e_log_returns(
        "2020-01-01", "2020-01-10", cache_dir=tmp_path, loader=counting_loader
    )

    assert calls["count"] == 1
    assert second.source == "cache"
    assert first.series.equals(second.series)


_STOXX_FILE_SAMPLE = """EURO STOXX 50 Volatility Indices,,,,,,,,,
 ,VSTOXX,Sub-Index 1M,Sub-Index 2M,Sub-Index 3M,Sub-Index 6M,Sub-Index 9M,Sub-Index 12M,Sub-Index 18M,Sub-Index 24M
Date,V2TX,V6I1,V6I2,V6I3,V6I4,V6I5,V6I6,V6I7,V6I8
04.01.1999,18.2033,21.2458,17.5555,31.2179,33.3124,33.7327,33.2232,31.8535,23.8209
05.01.1999,29.6912,36.6400,28.4274,32.6922,33.7326,33.1724,32.8457,32.2904,25.0532
06.01.1999,NA,25.4107,25.1351,32.2186,32.6459,31.9673,32.9260,33.2871,26.0107
"""


def test_load_vstoxx_history_parses_the_documented_file_shape() -> None:
    history = sh.load_vstoxx_history(fetch=lambda: _STOXX_FILE_SAMPLE)

    assert history.observations == 2  # the NA row is dropped
    assert history.start == "1999-01-04"
    assert history.end == "1999-01-05"
    assert history.level.iloc[0] == pytest.approx(18.2033)


def test_load_vstoxx_history_rejects_an_implausible_value() -> None:
    bad_sample = _STOXX_FILE_SAMPLE.replace("18.2033", "999.0")

    with pytest.raises(sh.VstoxxHistoryError):
        sh.load_vstoxx_history(fetch=lambda: bad_sample)


def test_load_vstoxx_history_rejects_an_unexpected_header() -> None:
    with pytest.raises(sh.VstoxxHistoryError):
        sh.load_vstoxx_history(fetch=lambda: "not,the,right,shape\n1,2,3,4\n")


def test_load_vstoxx_history_default_reads_the_checked_in_fixture() -> None:
    # No injected fetch: exercises the real bundled fixture file and its checksum
    # guard end to end, not a double. Values are the documented frozen history.
    history = sh.load_vstoxx_history()

    assert history.observations == 4357
    assert history.start == "1999-01-04"
    assert history.end == "2016-02-12"
    assert history.level.iloc[0] == pytest.approx(18.2033)


def test_verify_and_decode_rejects_bytes_that_do_not_match_the_recorded_checksum() -> (
    None
):
    with pytest.raises(sh.FixtureIntegrityError):
        sh._verify_and_decode(b"this is not the fixture")

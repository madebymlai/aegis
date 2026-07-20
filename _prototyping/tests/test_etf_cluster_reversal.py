from __future__ import annotations

import numpy as np
import pandas as pd

from _prototyping.etf_cluster_reversal.backtest import (
    BacktestConfig,
    HistoricalEligibility,
    evaluate_target_path,
    walk_forward_targets,
)
from _prototyping.etf_cluster_reversal.ib_history import (
    AssetHistory,
    history_to_state,
)
from _prototyping.etf_cluster_reversal.model import (
    FORMATION_DAYS,
    PrototypeState,
    initial_state,
    state_from_history,
)
from _prototyping.etf_cluster_reversal.universe import UCITS_UNIVERSE


def _frame(prices: np.ndarray, volumes: np.ndarray) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-02", periods=len(prices), tz="UTC")
    return pd.DataFrame(
        {
            "Open": prices * 0.999,
            "High": prices * 1.002,
            "Low": prices * 0.998,
            "Close": prices,
            "Volume": volumes,
        },
        index=index,
    )


def _prices(days: int, phase: float) -> np.ndarray:
    time = np.arange(days, dtype=float)
    daily_returns = (
        0.0003
        + 0.002 * np.sin(time / (5.0 + 3.0 * phase) + phase)
        + 0.001 * np.cos(time / (11.0 + phase))
    )
    return 100.0 * np.exp(np.cumsum(daily_returns))


def _all_eligible(state: PrototypeState) -> HistoricalEligibility:
    returns = state.returns
    return HistoricalEligibility(
        dollar_volumes=pd.DataFrame(
            1_000_000.0, index=returns.index, columns=returns.columns
        ),
        family_by_ticker={ticker: "test" for ticker in returns.columns},
        minimum_median_dollar_volume=0.0,
    )


def test_ucits_universe_has_the_expected_london_instrument_identities() -> None:
    instrument_ids = tuple(candidate.instrument_id for candidate in UCITS_UNIVERSE)

    assert instrument_ids == (
        "CSPX.LSEETF",
        "IUIT.LSEETF",
        "SXLK.LSEETF",
        "XUTC.LSEETF",
        "IUHC.LSEETF",
        "SXLV.LSEETF",
        "XUHC.LSEETF",
        "IUFS.LSEETF",
        "SXLF.LSEETF",
        "XUFN.LSEETF",
    )


def test_live_state_keeps_the_prior_month_cluster_freeze() -> None:
    index = pd.bdate_range("2025-01-02", periods=165, tz="UTC")
    time = np.arange(165, dtype=float)
    market = pd.Series(0.004 * np.sin(time / 9.0), index=index, name="CSPX")
    common = 0.003 * np.cos(time / 7.0)
    returns = pd.DataFrame(
        {
            "AAA": market.to_numpy() + common + 0.002 * np.sin(time / 3.0),
            "BBB": market.to_numpy() + common + 0.002 * np.cos(time / 4.0),
            "CCC": market.to_numpy() + common - 0.002 * np.sin(time / 5.0),
        },
        index=index,
    )
    volumes = pd.DataFrame(1_000_000.0, index=index, columns=returns.columns)
    gaps = pd.DataFrame(0.0, index=index, columns=returns.columns)

    state = state_from_history(returns, market, volumes, gaps)

    assert state.clusters.formed_on == "2025-07-22"


def test_history_to_state_applies_cash_distribution_to_total_return() -> None:
    days = FORMATION_DAYS + 45
    volumes = np.full(days, 1_000_000.0)
    benchmark_frame = _frame(_prices(days, 0.0), volumes)
    aaa_prices = _prices(days, 0.4)
    aaa_prices[-1] = aaa_prices[-2] - 1.0
    aaa_frame = _frame(aaa_prices, volumes)
    distribution_date = aaa_frame.index[-1].normalize()
    histories = {
        "CSPX": AssetHistory("CSPX", "benchmark", "CSPX.LSEETF", benchmark_frame, {}),
        "AAA": AssetHistory(
            "AAA",
            "test",
            "AAA.LSEETF",
            aaa_frame,
            {distribution_date: 1.0},
        ),
        "BBB": AssetHistory(
            "BBB",
            "test",
            "BBB.LSEETF",
            _frame(_prices(days, 0.8), volumes),
            {},
        ),
        "CCC": AssetHistory(
            "CCC",
            "test",
            "CCC.LSEETF",
            _frame(_prices(days, 1.2), volumes),
            {},
        ),
    }

    loaded = history_to_state(histories, benchmark="CSPX")

    assert loaded.state.returns.loc[distribution_date, "AAA"] == 0.0


def test_execution_return_starts_one_session_after_the_signal() -> None:
    days = FORMATION_DAYS + 45
    volumes = np.full(days, 1_000_000.0)
    benchmark_frame = _frame(_prices(days, 0.0), volumes)
    aaa_frame = _frame(_prices(days, 0.4), volumes)
    aaa_frame.loc[aaa_frame.index[-5:], "Open"] = [99.0, 100.0, 101.0, 102.0, 103.0]
    distribution_date = aaa_frame.index[-3].normalize()
    signal_date_before_entry = aaa_frame.index[-5].normalize()
    signal_date_on_entry = aaa_frame.index[-4].normalize()
    histories = {
        "CSPX": AssetHistory("CSPX", "benchmark", "CSPX.LSEETF", benchmark_frame, {}),
        "AAA": AssetHistory(
            "AAA", "test", "AAA.LSEETF", aaa_frame, {distribution_date: 1.0}
        ),
        "BBB": AssetHistory(
            "BBB",
            "test",
            "BBB.LSEETF",
            _frame(_prices(days, 0.8), volumes),
            {},
        ),
        "CCC": AssetHistory(
            "CCC",
            "test",
            "CCC.LSEETF",
            _frame(_prices(days, 1.2), volumes),
            {},
        ),
    }

    loaded = history_to_state(histories, benchmark="CSPX")

    np.testing.assert_allclose(
        loaded.execution_returns.loc[signal_date_before_entry, "AAA"],
        0.01980262729617973,
    )
    np.testing.assert_allclose(
        loaded.execution_returns.loc[signal_date_on_entry, "AAA"],
        0.00985229644301164,
    )


def _two_day_target_path() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.bdate_range("2026-01-05", periods=2, tz="UTC")
    targets = pd.DataFrame({"AAA": [0.5, 0.5], "BBB": [-0.5, -0.5]}, index=index)
    execution_returns = pd.DataFrame(
        {"AAA": [np.log(1.02), 0.0], "BBB": [0.0, 0.0]}, index=index
    )
    return targets, execution_returns


def test_target_path_earns_the_supplied_execution_return() -> None:
    targets, execution_returns = _two_day_target_path()

    daily = evaluate_target_path(
        targets,
        execution_returns,
        BacktestConfig(transaction_cost_bps=0.0, annual_short_borrow_bps=0.0),
    )

    np.testing.assert_allclose(daily["gross_return"], [0.01, 0.0])


def test_target_path_charges_entry_and_terminal_liquidation_turnover() -> None:
    targets, execution_returns = _two_day_target_path()

    daily = evaluate_target_path(
        targets,
        execution_returns,
        BacktestConfig(transaction_cost_bps=0.0, annual_short_borrow_bps=0.0),
    )

    np.testing.assert_allclose(daily["turnover"], [1.0, 1.0])


def test_target_path_charges_transaction_costs() -> None:
    targets, execution_returns = _two_day_target_path()

    daily = evaluate_target_path(
        targets,
        execution_returns,
        BacktestConfig(transaction_cost_bps=10.0, annual_short_borrow_bps=0.0),
    )

    np.testing.assert_allclose(daily["transaction_cost"], [0.001, 0.001])


def test_target_path_charges_short_borrow_costs() -> None:
    targets, execution_returns = _two_day_target_path()

    daily = evaluate_target_path(
        targets,
        execution_returns,
        BacktestConfig(transaction_cost_bps=0.0, annual_short_borrow_bps=252.0),
    )

    np.testing.assert_allclose(daily["borrow_cost"], [0.00005, 0.00005])


def test_target_path_subtracts_costs_from_net_return() -> None:
    targets, execution_returns = _two_day_target_path()

    daily = evaluate_target_path(
        targets,
        execution_returns,
        BacktestConfig(transaction_cost_bps=10.0, annual_short_borrow_bps=252.0),
    )

    np.testing.assert_allclose(daily["net_return"], [0.00895, -0.00105])


def test_historical_eligibility_uses_only_data_through_the_formation_date() -> None:
    index = pd.bdate_range("2025-01-02", periods=140, tz="UTC")
    dollar_volumes = pd.DataFrame(
        1_000_000.0, index=index, columns=["AAA", "BBB", "CCC"]
    )
    dollar_volumes.loc[index[70] :, "AAA"] = 10.0
    eligibility = HistoricalEligibility(
        dollar_volumes=dollar_volumes,
        family_by_ticker={"AAA": "test", "BBB": "test", "CCC": "test"},
        minimum_median_dollar_volume=250_000.0,
    )

    before_future_drop = eligibility.eligible_tickers(index[69])
    after_drop_enters_lookback = eligibility.eligible_tickers(index[-1])

    assert before_future_drop == ("AAA", "BBB", "CCC")
    assert after_drop_enters_lookback == ()


def test_walk_forward_targets_do_not_change_before_future_data_changes() -> None:
    original = initial_state()
    changed_returns = original.returns.copy()
    changed_returns.iloc[-3:, 0] += 0.10
    changed = original.__class__(
        day=original.day,
        returns=changed_returns,
        market=original.market,
        volumes=original.volumes,
        gaps=original.gaps,
        clusters=original.clusters,
        positions=original.positions,
        targets=original.targets,
        last_action=original.last_action,
    )

    original_path = walk_forward_targets(original, _all_eligible(original))
    changed_path = walk_forward_targets(changed, _all_eligible(changed))

    pd.testing.assert_frame_equal(
        original_path.targets.iloc[:-3], changed_path.targets.iloc[:-3]
    )


def test_history_to_state_excludes_illiquid_assets_before_clustering() -> None:
    days = FORMATION_DAYS + 45
    liquid = np.full(days, 1_000_000.0)
    illiquid = np.full(days, 10.0)
    histories = {
        "CSPX": AssetHistory(
            "CSPX",
            "benchmark",
            "CSPX.LSEETF",
            _frame(_prices(days, 0.0), liquid),
            {},
        ),
        "AAA": AssetHistory(
            "AAA",
            "test",
            "AAA.LSEETF",
            _frame(_prices(days, 0.4), liquid),
            {},
        ),
        "BBB": AssetHistory(
            "BBB",
            "test",
            "BBB.LSEETF",
            _frame(_prices(days, 0.8), liquid),
            {},
        ),
        "CCC": AssetHistory(
            "CCC",
            "test",
            "CCC.LSEETF",
            _frame(_prices(days, 1.2), liquid),
            {},
        ),
        "THIN": AssetHistory(
            "THIN",
            "test",
            "THIN.LSEETF",
            _frame(_prices(days, 1.6), illiquid),
            {},
        ),
    }

    loaded = history_to_state(
        histories, benchmark="CSPX", minimum_median_dollar_volume=1_000_000.0
    )

    assert tuple(loaded.state.returns.columns) == ("AAA", "BBB", "CCC")
    assert loaded.excluded[0].ticker == "THIN"
    assert loaded.excluded[0].reason == "median dollar volume below $1,000,000"


def test_history_to_state_excludes_an_incomplete_peer_family() -> None:
    days = FORMATION_DAYS + 45
    volumes = np.full(days, 1_000_000.0)
    histories = {
        "CSPX": AssetHistory(
            "CSPX",
            "benchmark",
            "CSPX.LSEETF",
            _frame(_prices(days, 0.0), volumes),
            {},
        ),
        "AAA": AssetHistory(
            "AAA",
            "complete",
            "AAA.LSEETF",
            _frame(_prices(days, 0.4), volumes),
            {},
        ),
        "BBB": AssetHistory(
            "BBB",
            "complete",
            "BBB.LSEETF",
            _frame(_prices(days, 0.8), volumes),
            {},
        ),
        "CCC": AssetHistory(
            "CCC",
            "complete",
            "CCC.LSEETF",
            _frame(_prices(days, 1.2), volumes),
            {},
        ),
        "DDD": AssetHistory(
            "DDD",
            "incomplete",
            "DDD.LSEETF",
            _frame(_prices(days, 1.6), volumes),
            {},
        ),
        "EEE": AssetHistory(
            "EEE",
            "incomplete",
            "EEE.LSEETF",
            _frame(_prices(days, 2.0), volumes),
            {},
        ),
    }

    loaded = history_to_state(histories, benchmark="CSPX")

    assert tuple(loaded.state.returns.columns) == ("AAA", "BBB", "CCC")
    assert {item.ticker for item in loaded.excluded} == {"DDD", "EEE"}

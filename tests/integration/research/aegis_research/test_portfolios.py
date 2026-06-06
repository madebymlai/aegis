import numpy as np
import pandas as pd
import pytest

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.portfolios import (
    PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION,
    PortfolioSimulationResult,
    expand_market_frame_to_candidate_columns,
    simulate_portfolio,
    simulate_portfolio_batch,
)


def test_simulate_portfolio_returns_result_and_v3_diagnostics_schema_version() -> None:
    close, allocations = _two_symbol_inputs()

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))

    assert isinstance(result, PortfolioSimulationResult)
    assert result.diagnostics["schema_version"] == PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION


def test_nan_allocations_row_does_not_rebalance_and_positions_persist() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0, 20.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, np.nan, np.nan], "B": [0.5, np.nan, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))
    alloc_dates = [row[0] for row in result.diagnostics["allocations"]["rebalance_rows"]]

    assert alloc_dates == ["2024-01-01T00:00:00", "2024-01-04T00:00:00"]
    holdings_before_terminal = result.portfolio.assets.iloc[-2]
    assert holdings_before_terminal["A"] > 0
    assert holdings_before_terminal["B"] > 0


def test_all_zero_allocations_row_in_non_terminal_location_closes_positions_at_close() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0, 20.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, 0.0, np.nan, np.nan], "B": [0.5, 0.0, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))
    assets = result.portfolio.assets

    assert assets.iloc[1].to_dict() == pytest.approx({"A": 0.0, "B": 0.0})
    orders = result.portfolio.orders.records_readable
    second_bar_orders = orders[orders["Index"].astype(str) == "2024-01-02"]
    assert set(second_bar_orders["Side"]) == {"Sell"}
    assert (second_bar_orders["Price"] == 10.0).any()
    assert (second_bar_orders["Price"] == 20.0).any()


def test_full_a_to_full_b_switch_under_shared_cash_executes_single_rebalance() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0, 20.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [1.0, np.nan, 0.0, np.nan], "B": [0.0, np.nan, 1.0, np.nan]},
        index=index,
    )

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))
    orders = result.portfolio.orders.records_readable
    third_bar = orders[orders["Index"].astype(str) == "2024-01-03"]
    sides_by_symbol = {row["Column"]: row["Side"] for _, row in third_bar.iterrows()}

    assert sides_by_symbol == {"A": "Sell", "B": "Buy"}
    assert result.portfolio.assets.iloc[2]["A"] == pytest.approx(0.0)
    assert result.portfolio.assets.iloc[2]["B"] > 0


def test_consecutive_identical_target_rows_appear_as_separate_rebalance_records() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0, 20.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, 0.5, np.nan, np.nan], "B": [0.5, 0.5, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))
    alloc_dates = [row[0] for row in result.diagnostics["allocations"]["rebalance_rows"]]

    assert "2024-01-01T00:00:00" in alloc_dates
    assert "2024-01-02T00:00:00" in alloc_dates


def test_terminal_liquidation_sells_all_held_positions_at_last_close() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 21.0, 22.0, 23.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, np.nan, np.nan], "B": [0.5, np.nan, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))
    final_assets = result.portfolio.assets.iloc[-1]
    final_cash = float(result.portfolio.cash.iloc[-1])
    final_equity = float(result.portfolio.value.iloc[-1])

    assert final_assets.to_dict() == pytest.approx({"A": 0.0, "B": 0.0})
    assert final_cash == pytest.approx(final_equity)
    orders = result.portfolio.orders.records_readable
    last_bar = orders[orders["Index"].astype(str) == "2024-01-04"]
    assert set(last_bar["Side"]) == {"Sell"}
    assert set(last_bar["Column"]) == {"A", "B"}


def test_batched_three_candidate_run_preserves_candidate_identity_in_pfo_columns() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 21.0, 22.0, 23.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-a", "cand-b", "cand-c"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], :] = 0.5

    result = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0, slippage=0)
    )

    assert result.diagnostics["grouping"]["candidate_ids"] == [
        "cand-a",
        "cand-b",
        "cand-c",
    ]
    assert result.diagnostics["grouping"]["group_by"] == "except_level:symbol"
    assert result.diagnostics["grouping"]["group_count"] == 3
    candidate_index = result.portfolio.wrapper.grouper.get_index()
    assert list(candidate_index) == ["cand-a", "cand-b", "cand-c"]
    pf_columns = result.portfolio.wrapper.columns
    assert set(pf_columns) == {
        ("cand-a", "A"), ("cand-a", "B"),
        ("cand-b", "A"), ("cand-b", "B"),
        ("cand-c", "A"), ("cand-c", "B"),
    }


def test_signed_both_direction_run_opens_a_real_short_position() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 21.0, 22.0, 23.0]},
        index=index,
    )
    # One long (+0.5) and one short (-0.5) target weight: a signed book.
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, np.nan, np.nan], "B": [-0.5, np.nan, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(fees=0, slippage=0, gross_cap=1.0, direction="both"),
    )

    assets = result.portfolio.assets
    assert assets.iloc[1]["A"] > 0
    assert assets.iloc[1]["B"] < 0
    realized = result.portfolio.get_allocations(group_by=False)
    assert realized.iloc[1]["B"] < 0


def test_default_longonly_run_holds_only_long_positions() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 21.0, 22.0, 23.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, np.nan, np.nan], "B": [0.5, np.nan, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0))

    assets = result.portfolio.assets
    assert (assets.iloc[1] >= 0).all()
    assert result.diagnostics["vbt_settings"]["direction"] == "longonly"


def test_diagnostics_record_leverage_kwargs_from_gross_cap() -> None:
    close, allocations = _two_symbol_inputs()

    diagnostics = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(fees=0, slippage=0, gross_cap=2.0, direction="both"),
    ).diagnostics

    assert diagnostics["vbt_settings"]["leverage"] == 2.0
    assert diagnostics["vbt_settings"]["leverage_mode"] == "eager"
    assert diagnostics["vbt_settings"]["direction"] == "both"


def test_split_gap_row_is_masked_before_pfo_and_counted_in_non_executable_diagnostics() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)
    split_index = market_index[[0, 1, 3, 4]]
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 13.0, 14.0], "B": [20.0, 21.0, 23.0, 24.0]},
        index=split_index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, 0.5, 0.5, np.nan], "B": [0.5, 0.5, 0.5, np.nan]},
        index=split_index,
    )

    result = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(fees=0, slippage=0),
        market_index=market_index,
    )

    assert result.diagnostics["non_executable"]["non_executable_rows"] == 1
    assert result.diagnostics["non_executable"]["non_executable_by_symbol"] == {
        "A": 1,
        "B": 1,
    }
    assert result.diagnostics["non_executable"]["terminal_liquidation"] is True
    alloc_dates = [row[0] for row in result.diagnostics["allocations"]["rebalance_rows"]]
    assert "2024-01-04T00:00:00" not in alloc_dates
    assert "2024-01-05T00:00:00" in alloc_dates


def test_diagnostics_v3_payload_contains_required_blocks_and_no_legacy_fields() -> None:
    close, allocations = _two_symbol_inputs()

    diagnostics = simulate_portfolio(
        close, allocations, PortfolioConfig(fees=0, slippage=0)
    ).diagnostics

    assert diagnostics["schema_version"] == "portfolio_diagnostics.v3"
    assert diagnostics["vbt_settings"]["factory"] == "Portfolio.from_optimizer"
    assert diagnostics["vbt_settings"]["pf_method"] == "from_orders"
    assert diagnostics["vbt_settings"]["size_type"] == "targetpercent"
    assert diagnostics["vbt_settings"]["cash_sharing"] is True
    assert diagnostics["vbt_settings"]["call_seq"] == "auto"
    assert diagnostics["vbt_settings"]["one_order_per_bar"] is True
    assert diagnostics["contract"]["execution_timing"] == "same_close"
    assert diagnostics["contract"]["terminal_liquidation"] is True
    assert diagnostics["contract"]["gross_cap"] == 1.0
    assert diagnostics["contract"]["net_cap"] == 1.0
    assert "direction_scope" not in diagnostics["contract"]
    assert set(diagnostics["allocations"]) == {
        "rebalance_rows",
        "requested",
        "realized_at_fill",
    }
    assert set(diagnostics["order_rejections"]) == {
        "NoCash",
        "PartialFill",
        "SizeNaN",
        "SizeZero",
    }
    assert set(diagnostics["non_executable"]) == {
        "non_executable_rows",
        "non_executable_by_symbol",
        "terminal_liquidation",
    }
    not_applicable = diagnostics["contract"]["not_applicable_vbt_settings"]
    assert "upon_short_conflict" in not_applicable
    assert "upon_opposite_entry" in not_applicable
    for legacy_field in (
        "allocation_mode",
        "entry_budget",
        "sizing",
        "raw_signals",
        "simulation_signals",
        "rebalances_existing_positions",
    ):
        assert legacy_field not in diagnostics
        for block in diagnostics.values():
            if isinstance(block, dict):
                assert legacy_field not in block


def test_diagnostics_records_realized_weights_at_each_rebalance_row() -> None:
    close, allocations = _two_symbol_inputs()

    diagnostics = simulate_portfolio(
        close, allocations, PortfolioConfig(fees=0, slippage=0)
    ).diagnostics
    realized = diagnostics["allocations"]["realized_at_fill"]

    assert len(realized) == len(diagnostics["allocations"]["rebalance_rows"])
    for record in realized:
        assert set(record["weights"]) == {"A", "B"}


def test_expand_market_frame_to_candidate_columns_preserves_candidate_symbol_order() -> None:
    close = pd.DataFrame(
        {"SYN": [10.0, 11.0, 12.0, 13.0]},
        index=pd.date_range("2024-01-01", periods=4),
    )
    target_columns = pd.MultiIndex.from_tuples(
        [("candidate-b", "SYN"), ("candidate-a", "SYN")],
        names=["candidate_id", "symbol"],
    )

    expanded = expand_market_frame_to_candidate_columns(
        close, target_columns, feature_name="Close"
    )

    assert expanded.columns.equals(target_columns)
    assert expanded[("candidate-b", "SYN")].tolist() == close["SYN"].tolist()
    assert expanded[("candidate-a", "SYN")].tolist() == close["SYN"].tolist()


def test_portfolio_inputs_reject_symbol_mismatches_instead_of_dropping_columns() -> None:
    close, allocations = _two_symbol_inputs()
    allocations["EXTRA"] = 0.0

    with pytest.raises(ValueError, match="columns"):
        simulate_portfolio(close, allocations, PortfolioConfig())


def test_portfolio_inputs_reject_index_mismatches_instead_of_dropping_rows() -> None:
    close, allocations = _two_symbol_inputs()
    allocations = allocations.iloc[:-1]

    with pytest.raises(ValueError, match="index"):
        simulate_portfolio(close, allocations, PortfolioConfig())


def _two_symbol_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 21.0, 22.0, 23.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, 0.5, np.nan], "B": [0.5, np.nan, 0.5, np.nan]},
        index=index,
    )
    return close, allocations

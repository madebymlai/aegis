import pandas as pd
import pytest

from research.aegis_research.config import PortfolioConfig, SignalConfig
from research.aegis_research.portfolios import PortfolioSimulationResult, simulate_portfolio


def test_next_open_simulation_uses_open_prices_and_records_diagnostics() -> None:
    close, open_prices, entries, exits = _portfolio_inputs()

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(fees=0, slippage=0),
        SignalConfig(),
        open_prices=open_prices,
    )
    orders = result.portfolio.orders.records_readable

    assert isinstance(result, PortfolioSimulationResult)
    assert orders["Price"].tolist() == [11.5, 13.5]
    assert result.diagnostics["execution"]["timing"] == "next_open"
    assert result.diagnostics["execution"]["vbt_price"] == "nextopen"
    assert result.diagnostics["vbt_settings"]["upon_long_conflict"] == "ignore"
    assert result.diagnostics["contract"]["not_applicable_vbt_settings"]["upon_short_conflict"] == (
        "not_applicable_long_only_v1"
    )
    assert result.diagnostics["records"]["order_count"] == 2
    assert result.diagnostics["records"]["trade_count"] == 1


def test_same_close_simulation_does_not_require_open_prices() -> None:
    close, _open_prices, entries, exits = _portfolio_inputs()

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(fees=0, slippage=0),
        SignalConfig(execution_timing="same_close"),
    )

    orders = result.portfolio.orders.records_readable

    assert orders["Price"].tolist() == [10.0, 12.0]
    assert result.diagnostics["execution"]["timing"] == "same_close"
    assert result.diagnostics["execution"]["vbt_price"] == "close"


def test_entry_budget_is_split_across_same_bar_executable_entries() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0], "B": [20.0, 21.0, 22.0]},
        index=index,
    )
    open_prices = close + 0.5
    entries = pd.DataFrame(
        {"A": [True, False, False], "B": [True, False, False]},
        index=index,
    )
    exits = pd.DataFrame(False, index=index, columns=close.columns)

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=0.6, fees=0, slippage=0),
        SignalConfig(),
        open_prices=open_prices,
    )
    orders = result.portfolio.orders.records_readable

    assert result.diagnostics["vbt_settings"]["factory"] == "Portfolio.from_signals"
    assert result.diagnostics["vbt_settings"]["size_type"] == "valuepercent"
    assert result.diagnostics["vbt_settings"]["cash_sharing"] is True
    assert result.diagnostics["vbt_settings"]["group_by"] is True
    assert result.diagnostics["vbt_settings"]["call_seq"] == "auto"
    assert "predetermined" in result.diagnostics["vbt_settings"]["call_sequence_caveat"]
    assert result.diagnostics["contract"]["allocation_mode"] == "event_style_signals"
    assert result.diagnostics["contract"]["entry_budget"] == 0.6
    assert result.diagnostics["contract"]["rebalances_existing_positions"] is False
    assert result.diagnostics["grouping"] == {
        "cash_sharing": True,
        "group_by": True,
        "group_count": 1,
        "group_scope": "all_symbols_single_cash_pool",
    }
    assert result.diagnostics["sizing"]["active_entry_rows"] == 1
    assert result.diagnostics["sizing"]["max_entries_per_row"] == 2
    assert result.diagnostics["sizing"]["nonzero_size_cells"] == 2
    assert result.diagnostics["sizing"]["min_nonzero_valuepercent"] == pytest.approx(0.3)
    assert result.diagnostics["sizing"]["max_nonzero_valuepercent"] == pytest.approx(0.3)
    assert result.diagnostics["records"]["order_count"] == 2
    assert result.diagnostics["records"]["orders_per_group"] == {"portfolio": 2}
    assert result.diagnostics["records"]["orders_per_symbol"] == {"A": 1, "B": 1}
    assert (orders["Size"] * orders["Price"]).tolist() == pytest.approx([3000.0, 3000.0])


def test_single_entry_uses_explicit_entry_budget_not_implicit_full_allocation() -> None:
    close, open_prices, entries, exits = _portfolio_inputs()

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=0.6, fees=0, slippage=0),
        SignalConfig(),
        open_prices=open_prices,
    )
    orders = result.portfolio.orders.records_readable

    assert result.diagnostics["sizing"]["active_entry_rows"] == 1
    assert result.diagnostics["sizing"]["max_entries_per_row"] == 1
    assert result.diagnostics["sizing"]["min_nonzero_valuepercent"] == pytest.approx(0.6)
    assert result.diagnostics["sizing"]["max_nonzero_valuepercent"] == pytest.approx(0.6)
    assert (orders["Size"] * orders["Price"]).iloc[0] == pytest.approx(6000.0)


def test_same_bar_shared_cash_exit_can_fund_new_entry() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0, 10.0], "B": [10.0, 10.0, 10.0, 10.0]},
        index=index,
    )
    entries = pd.DataFrame(
        {"A": [True, False, False, False], "B": [False, False, True, False]},
        index=index,
    )
    exits = pd.DataFrame(
        {"A": [False, False, True, False], "B": [False, False, False, False]},
        index=index,
    )

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=1.0, fees=0, slippage=0),
        SignalConfig(execution_timing="same_close"),
    )
    orders = result.portfolio.orders.records_readable

    assert orders["Column"].tolist() == ["A", "A", "B"]
    assert orders["Side"].tolist() == ["Buy", "Sell", "Buy"]
    assert orders["Signal Index"].astype(str).tolist() == [
        "2024-01-01",
        "2024-01-03",
        "2024-01-03",
    ]
    assert result.diagnostics["records"]["order_count"] == 3
    assert result.diagnostics["records"]["orders_per_symbol"] == {"A": 2, "B": 1}


def test_later_entries_do_not_rebalance_existing_positions() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0, 20.0]},
        index=index,
    )
    entries = pd.DataFrame(
        {"A": [True, False, False, False], "B": [False, False, True, False]},
        index=index,
    )
    exits = pd.DataFrame(False, index=index, columns=close.columns)

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(entry_budget=0.4, fees=0, slippage=0),
        SignalConfig(execution_timing="same_close"),
    )
    orders = result.portfolio.orders.records_readable

    assert orders["Column"].tolist() == ["A", "B"]
    assert orders["Side"].tolist() == ["Buy", "Buy"]
    assert orders["Signal Index"].astype(str).tolist() == ["2024-01-01", "2024-01-03"]
    assert orders.loc[orders["Column"] == "A", "Size"].iloc[0] == pytest.approx(400.0)


def test_repeated_raw_entries_are_delegated_to_vbt_order_resolution() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame({"SYN": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=index)
    open_prices = close + 0.5
    entries = pd.DataFrame({"SYN": [True, True, True, False, False]}, index=index)
    exits = pd.DataFrame({"SYN": [False, False, False, True, False]}, index=index)

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(fees=0, slippage=0),
        SignalConfig(),
        open_prices=open_prices,
    )

    assert result.diagnostics["raw_signals"]["raw_entry_states"] == 3
    assert result.diagnostics["simulation_signals"]["entry_states"] == 3
    assert result.diagnostics["records"]["order_count"] == 2
    assert result.diagnostics["records"]["trade_count"] == 1


def test_next_open_requires_open_prices() -> None:
    close, _open_prices, entries, exits = _portfolio_inputs()

    with pytest.raises(ValueError, match="open prices"):
        simulate_portfolio(
            close,
            entries,
            exits,
            PortfolioConfig(),
            SignalConfig(),
        )


def test_next_open_rejects_null_execution_open_prices() -> None:
    close, open_prices, entries, exits = _portfolio_inputs()
    open_prices.loc[open_prices.index[1], "SYN"] = pd.NA

    with pytest.raises(ValueError, match="Open"):
        simulate_portfolio(
            close,
            entries,
            exits,
            PortfolioConfig(),
            SignalConfig(),
            open_prices=open_prices,
        )


def test_portfolio_inputs_reject_symbol_mismatches_instead_of_dropping_columns() -> None:
    close, open_prices, entries, exits = _portfolio_inputs()
    entries["EXTRA"] = False

    with pytest.raises(ValueError, match="columns"):
        simulate_portfolio(
            close,
            entries,
            exits,
            PortfolioConfig(),
            SignalConfig(),
            open_prices=open_prices,
        )


def test_portfolio_inputs_reject_index_mismatches_instead_of_dropping_rows() -> None:
    close, open_prices, entries, exits = _portfolio_inputs()
    entries = entries.iloc[:-1]

    with pytest.raises(ValueError, match="index"):
        simulate_portfolio(
            close,
            entries,
            exits,
            PortfolioConfig(),
            SignalConfig(),
            open_prices=open_prices,
        )


def test_last_bar_next_open_signal_is_non_executable_within_split() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame({"SYN": [10.0, 11.0, 12.0]}, index=index)
    open_prices = close + 0.5
    entries = pd.DataFrame({"SYN": [False, False, True]}, index=index)
    exits = pd.DataFrame({"SYN": [False, False, False]}, index=index)

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(fees=0, slippage=0),
        SignalConfig(),
        open_prices=open_prices,
    )

    assert result.diagnostics["execution"]["terminal_non_executable_signals"] == 1
    assert result.diagnostics["sizing"]["nonzero_size_cells"] == 0
    assert result.diagnostics["records"]["order_count"] == 0


def test_next_open_signal_before_market_index_gap_is_non_executable() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)
    split_index = market_index[[0, 1, 3, 4]]
    close = pd.DataFrame({"SYN": [10.0, 11.0, 13.0, 14.0]}, index=split_index)
    open_prices = close + 0.5
    entries = pd.DataFrame({"SYN": [False, True, False, False]}, index=split_index)
    exits = pd.DataFrame({"SYN": [False, False, False, False]}, index=split_index)

    result = simulate_portfolio(
        close,
        entries,
        exits,
        PortfolioConfig(fees=0, slippage=0),
        SignalConfig(),
        open_prices=open_prices,
        market_index=market_index,
    )

    assert result.diagnostics["execution"]["gap_non_executable_signals"] == 1
    assert result.diagnostics["execution"]["non_executable_signals"] == 1
    assert result.diagnostics["simulation_signals"]["entry_states"] == 0
    assert result.diagnostics["sizing"]["nonzero_size_cells"] == 0
    assert result.diagnostics["records"]["order_count"] == 0


def _portfolio_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"SYN": [10.0, 11.0, 12.0, 13.0]}, index=index)
    open_prices = close + 0.5
    entries = pd.DataFrame({"SYN": [True, False, False, False]}, index=index)
    exits = pd.DataFrame({"SYN": [False, False, True, False]}, index=index)
    return close, open_prices, entries, exits

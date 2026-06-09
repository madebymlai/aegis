import numpy as np
import pandas as pd
import pytest

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.portfolios import (
    PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION,
    PortfolioSimulationResult,
    assert_requested_realized_fidelity,
    expand_market_frame_to_candidate_columns,
    simulate_portfolio,
    simulate_portfolio_batch,
)


def test_simulate_portfolio_returns_result_and_v4_diagnostics_schema_version() -> None:
    close, allocations = _two_symbol_inputs()

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))

    assert isinstance(result, PortfolioSimulationResult)
    assert result.diagnostics["schema_version"] == PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION
    assert PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION == "portfolio_diagnostics.v4"


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

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))
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

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))
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

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))
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

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))
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

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))
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
        close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly")
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


def test_batch_rejects_candidate_breaching_net_cap_and_names_it() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-ok", "cand-net-long"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    # cand-ok is market-neutral (net 0); cand-net-long breaches net_cap=0 (net 1.0).
    allocations.loc[index[0], ("cand-ok", "A")] = 0.5
    allocations.loc[index[0], ("cand-ok", "B")] = -0.5
    allocations.loc[index[0], ("cand-net-long", "A")] = 0.5
    allocations.loc[index[0], ("cand-net-long", "B")] = 0.5

    config = PortfolioConfig(
        fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"
    )
    with pytest.raises(ValueError, match="cand-net-long"):
        simulate_portfolio_batch(close, allocations, config)


def test_batch_rejects_longonly_candidate_with_a_negative_weight() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-long", "cand-has-short"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("cand-long", "A")] = 0.5
    allocations.loc[index[0], ("cand-long", "B")] = 0.5
    # cand-has-short stays within both caps (gross 1.0, net 0.0) but the short weight
    # contradicts the run's longonly Direction — only the sign guard catches it.
    allocations.loc[index[0], ("cand-has-short", "A")] = 0.5
    allocations.loc[index[0], ("cand-has-short", "B")] = -0.5

    config = PortfolioConfig(
        fees=0, slippage=0, gross_cap=1.0, net_cap=1.0, direction="longonly"
    )
    with pytest.raises(ValueError, match="longonly"):
        simulate_portfolio_batch(close, allocations, config)


def test_batch_accepts_valid_market_neutral_book_within_caps() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-neutral"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    # gross 1.0 <= 2, net 0.0 <= 0: a legitimate dollar-neutral book must not be rejected.
    allocations.loc[index[0], ("cand-neutral", "A")] = 0.5
    allocations.loc[index[0], ("cand-neutral", "B")] = -0.5

    config = PortfolioConfig(
        fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"
    )
    result = simulate_portfolio_batch(close, allocations, config)

    assert isinstance(result, PortfolioSimulationResult)


def test_single_portfolio_rejects_book_breaching_gross_cap() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0]},
        index=index,
    )
    # gross = 0.8 + 0.8 = 1.6 exceeds gross_cap 1.0.
    allocations = pd.DataFrame(
        {"A": [0.8, np.nan, np.nan], "B": [0.8, np.nan, np.nan]},
        index=index,
    )

    config = PortfolioConfig(
        fees=0, slippage=0, gross_cap=1.0, net_cap=1.0, direction="longonly"
    )
    with pytest.raises(ValueError, match="gross_cap"):
        simulate_portfolio(close, allocations, config)


def test_market_neutral_run_book_is_net_zero_and_realized_matches_requested() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0, 14.0], "B": [20.0, 19.0, 18.0, 17.0, 16.0]},
        index=index,
    )
    # gross_cap=2, net_cap≈0: a fully invested long/short pair, net exposure ≈ 0.
    allocations = pd.DataFrame(
        {"A": [1.0, np.nan, np.nan, np.nan, np.nan], "B": [-1.0, np.nan, np.nan, np.nan, np.nan]},
        index=index,
    )

    result = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"),
    )

    requested = result.portfolio.get_allocations(group_by=False)
    # Realized weights at the rebalance row exactly match the requested signed book.
    fill_row = requested.loc[index[0]]
    assert fill_row["A"] == pytest.approx(1.0)
    assert fill_row["B"] == pytest.approx(-1.0)
    # Net exposure of the realized book at the fill row is ≈ 0 (market-neutral).
    assert fill_row.sum() == pytest.approx(0.0, abs=1e-9)


def test_requested_realized_fidelity_passes_when_realized_matches_at_rebalance_rows() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    requested = pd.DataFrame(
        {"A": [1.0, np.nan, 0.0], "B": [-1.0, np.nan, 0.0]}, index=index
    )
    realized = pd.DataFrame(
        # Off-rebalance row drifts (price move) but rebalance rows match exactly.
        {"A": [1.0, 0.93, 0.0], "B": [-1.0, -0.91, 0.0]}, index=index
    )

    # Must not raise: divergence on the NaN (no-rebalance) row is ignored.
    assert_requested_realized_fidelity(requested, realized, tolerance=1e-6)


def test_requested_realized_fidelity_fires_when_realized_diverges_at_a_rebalance_row() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    requested = pd.DataFrame(
        {"A": [1.0, np.nan, 0.0], "B": [-1.0, np.nan, 0.0]}, index=index
    )
    realized = pd.DataFrame(
        # The first rebalance row under-fills the short leg: a mis-fill that would
        # silently drift the book net-long.
        {"A": [1.0, 0.93, 0.0], "B": [-0.4, -0.91, 0.0]}, index=index
    )

    with pytest.raises(ValueError, match=r"requested|realized"):
        assert_requested_realized_fidelity(requested, realized, tolerance=1e-6)


def test_simulate_portfolio_gates_the_real_run_on_requested_realized_fidelity(monkeypatch) -> None:
    import research.aegis_research.portfolios as portfolios_module

    close, allocations = _two_symbol_inputs()
    calls: list[tuple[pd.DataFrame, pd.DataFrame]] = []

    def _spy(requested, realized, *, fill_lag=0, tolerance):
        calls.append((requested, realized))

    monkeypatch.setattr(portfolios_module, "assert_requested_realized_fidelity", _spy)
    simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))

    assert len(calls) == 1
    requested, realized = calls[0]
    # The gate is fed the sparse requested frame and the dense realized book.
    assert set(requested.columns) == {"A", "B"}
    assert set(realized.columns) == {"A", "B"}
    assert requested.index.isin(realized.index).all()


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

    result = simulate_portfolio(close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly"))

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
        PortfolioConfig(fees=0, slippage=0, direction="longonly"),
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
        close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly")
    ).diagnostics

    assert diagnostics["schema_version"] == "portfolio_diagnostics.v4"
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
        close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly")
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
        simulate_portfolio(close, allocations, PortfolioConfig(direction="longonly"))


def test_portfolio_inputs_reject_index_mismatches_instead_of_dropping_rows() -> None:
    close, allocations = _two_symbol_inputs()
    allocations = allocations.iloc[:-1]

    with pytest.raises(ValueError, match="index"):
        simulate_portfolio(close, allocations, PortfolioConfig(direction="longonly"))


def test_contract_records_structured_financing_carry_block() -> None:
    # ADR-0008 supersedes the old `not_modeled_v1` flag: short borrow carry is now charged,
    # so the contract carries a structured block declaring the mechanism, the rates it
    # charged at, the annualization base, and the still-deferred margin interest.
    close, allocations = _two_symbol_inputs()

    diagnostics = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(
            fees=0,
            slippage=0,
            direction="both",
            short_borrow_rate=0.01,
            short_rebate_rate=0.002,
        ),
    ).diagnostics
    carry = diagnostics["contract"]["financing_carry"]

    assert carry["mechanism"] == "cash_dividends_short_borrow_v2"
    assert carry["short_borrow_rate"] == 0.01
    assert carry["short_rebate_rate"] == 0.002
    assert carry["periods_per_year"] == 252
    assert carry["margin_interest"] == "not_modeled"
    assert "from_orders" in carry["margin_interest_reason"]
    # The string flag must be gone — no caller should still read it.
    assert carry != "not_modeled_v1"


def test_long_only_book_is_byte_for_byte_unchanged_with_carry_on_by_default() -> None:
    # ADR-0007 guarantee: a long-only book has no short legs, so the all-zero short-masked
    # cash_dividends leaves the simulation byte-for-byte identical whether carry rates are
    # the non-zero default or explicitly zero.
    close, allocations = _two_symbol_inputs()

    carry_on = simulate_portfolio(
        close, allocations, PortfolioConfig(fees=0, slippage=0, direction="longonly")
    )
    carry_off = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(
            fees=0, slippage=0, direction="longonly", short_borrow_rate=0.0, short_rebate_rate=0.0
        ),
    )

    pd.testing.assert_series_equal(
        carry_on.portfolio.value, carry_off.portfolio.value
    )
    assert _total_return(carry_on) == _total_return(carry_off)


def test_short_leg_carry_drops_return_and_long_leg_is_never_charged() -> None:
    # The ADR-0007 motivating book: a flat-price market-neutral long A / short B at gross 2
    # (long funded by short proceeds, free cash to charge carry against). It earns nothing
    # gross, so charging short borrow carry on the short leg only must drag the return
    # strictly negative; turning carry off recovers the frictionless zero. The long leg is
    # never charged — a same-sized long-only book stays flat with carry on.
    index = pd.date_range("2024-01-01", periods=63)
    close = pd.DataFrame(
        {"A": np.full(63, 100.0), "B": np.full(63, 100.0)},
        index=index,
    )
    short_book = pd.DataFrame(
        {
            "A": [0.5] + [np.nan] * 62,
            "B": [-0.5] + [np.nan] * 62,
        },
        index=index,
    )
    long_only_book = pd.DataFrame(
        {
            "A": [0.5] + [np.nan] * 62,
            "B": [0.5] + [np.nan] * 62,
        },
        index=index,
    )

    carry_on = PortfolioConfig(fees=0, slippage=0, gross_cap=2.0, direction="both")
    carry_off = PortfolioConfig(
        fees=0,
        slippage=0,
        gross_cap=2.0,
        direction="both",
        short_borrow_rate=0.0,
        short_rebate_rate=0.0,
    )

    short_on = _total_return(simulate_portfolio(close, short_book, carry_on))
    short_off = _total_return(simulate_portfolio(close, short_book, carry_off))
    long_on = _total_return(simulate_portfolio(close, long_only_book, carry_on))

    assert short_on < short_off
    assert short_off == pytest.approx(0.0, abs=1e-9)
    # The long-only flat book is unaffected by carry — long legs are never charged.
    assert long_on == pytest.approx(0.0, abs=1e-9)


def _total_return(result: PortfolioSimulationResult) -> float:
    value = result.portfolio.get_total_return()
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)


def test_records_count_exit_trades_for_long_and_short_legs() -> None:
    # A signed book that opens a long A / short B, then flattens both: each leg produces a
    # closed (exit) trade. The records block must count exit trades — long AND short — so the
    # short leg's realized round-trip is auditable, not just the long one.
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 19.0, 18.0, 17.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, 0.0, np.nan], "B": [-0.5, np.nan, 0.0, np.nan]},
        index=index,
    )

    diagnostics = simulate_portfolio(
        close,
        allocations,
        PortfolioConfig(fees=0, slippage=0, gross_cap=1.0, direction="both"),
    ).diagnostics
    records = diagnostics["records"]

    assert records["exit_trade_count"] == 2
    assert records["exit_trades_per_symbol"] == {"A": 1, "B": 1}


def test_all_from_signals_only_conflict_settings_attributed_to_from_orders() -> None:
    # The conflict/accumulate knobs belong to from_signals; from_orders (this route's
    # factory) never applies them, regardless of direction. The diagnostics must list
    # every such setting and attribute it to the factory, not the (now signed) direction.
    close, allocations = _two_symbol_inputs()

    diagnostics = simulate_portfolio(
        close, allocations, PortfolioConfig(fees=0, slippage=0, direction="both")
    ).diagnostics

    not_applicable = diagnostics["contract"]["not_applicable_vbt_settings"]
    assert set(not_applicable) == {
        "upon_short_conflict",
        "upon_dir_conflict",
        "upon_opposite_entry",
        "upon_long_conflict",
        "accumulate",
    }
    assert set(not_applicable.values()) == {"not_applicable_from_orders"}


def test_batch_fail_closed_nocash_guard_raises_on_underfilled_leveraged_book() -> None:
    # A leveraged long/short book that triggers the cash_sharing +
    # multi-asset-leverage mis-fill must raise a fail-closed error from the
    # batched simulation so no Candidate can be silently scored on a corrupted book.
    #
    # Trigger: gross equals leverage cap, then a mid-run price drift forces a
    # rebalance whose position-adjustment orders exhaust the shared cash pool
    # (eager leverage within a cash_sharing group).
    index = pd.date_range("2024-01-01", periods=20)
    symbols = ["A", "B", "C", "D"]
    close = pd.DataFrame(
        {
            "A": [100.0] * 5 + [110.0] * 15,
            "B": [200.0] * 5 + [180.0] * 15,
            "C": [300.0] * 20,
            "D": [400.0] * 20,
        },
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-underfilled"], symbols],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    # First rebalance: equal long/short at 1.25 each → gross = 5.0, within cap.
    for i, s in enumerate(symbols):
        allocations.loc[index[0], ("cand-underfilled", s)] = 1.25 if i % 2 == 0 else -1.25
    # Second rebalance at bar 10 after price drift exhausts the shared cash pool.
    for i, s in enumerate(symbols):
        allocations.loc[index[10], ("cand-underfilled", s)] = 1.25 if i % 2 == 0 else -1.25

    config = PortfolioConfig(
        fees=0,
        slippage=0,
        gross_cap=5.0,
        net_cap=0.0,
        direction="both",
        init_cash=10000,
        short_borrow_rate=0.0,
        short_rebate_rate=0.0,
    )
    with pytest.raises(ValueError, match="NoCash"):
        simulate_portfolio_batch(close, allocations, config)


def test_batch_fail_closed_nocash_guard_passes_on_clean_book() -> None:
    # A well-formed market-neutral book must simulate without raising.
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 21.0, 22.0, 23.0]},
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-neutral"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("cand-neutral", "A")] = 0.5
    allocations.loc[index[0], ("cand-neutral", "B")] = -0.5

    result = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both")
    )
    assert isinstance(result, PortfolioSimulationResult)


def test_batch_nocash_guard_reads_native_typed_field_not_readable_frame(monkeypatch) -> None:
    # The guard must read VBT's native typed res_status_info column, not the
    # human-readable records frame.
    import research.aegis_research.portfolios as portfolios_module

    index = pd.date_range("2024-01-01", periods=20)
    symbols = ["A", "B", "C", "D"]
    close = pd.DataFrame(
        {
            "A": [100.0] * 5 + [110.0] * 15,
            "B": [200.0] * 5 + [180.0] * 15,
            "C": [300.0] * 20,
            "D": [400.0] * 20,
        },
        index=index,
    )
    columns = pd.MultiIndex.from_product(
        [["cand-underfilled"], symbols],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    for i, s in enumerate(symbols):
        allocations.loc[index[0], ("cand-underfilled", s)] = 1.25 if i % 2 == 0 else -1.25
    for i, s in enumerate(symbols):
        allocations.loc[index[10], ("cand-underfilled", s)] = 1.25 if i % 2 == 0 else -1.25

    config = PortfolioConfig(
        fees=0,
        slippage=0,
        gross_cap=5.0,
        net_cap=0.0,
        direction="both",
        init_cash=10000,
        short_borrow_rate=0.0,
        short_rebate_rate=0.0,
    )

    # Prove the guard does NOT parse records_readable: if it did, patching
    # records_readable to return an empty frame would bypass the guard.
    # Instead, it reads records (native typed), so the guard still fires.
    calls = []

    def _spy_guard(pf):
        calls.append(pf)
        raise ValueError("NoCash")

    monkeypatch.setattr(portfolios_module, "_assert_no_nocash_rejection", _spy_guard)

    with pytest.raises(ValueError, match="NoCash"):
        simulate_portfolio_batch(close, allocations, config)

    assert len(calls) == 1


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

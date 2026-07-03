import numpy as np
import pandas as pd
import pytest
from aegis_data.distributions import Distribution
from aegis_runtime import DriftBand, gate
from nautilus_trader.model.identifiers import InstrumentId
from vectorbtpro import vbt
from vectorbtpro.portfolio.enums import OrderStatusInfo

from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.market_data.currency import CurrencyConversion
from research.aegis_research.portfolios import (
    _SINGLE_CANDIDATE_ID,
    distribution_cash_dividends,
    expand_market_frame_to_candidate_columns,
    simulate_portfolio_batch,
    simulate_single_book,
)
from tests.support.research.aegis_research.factories import make_portfolio_config


def _order_time_column(orders: pd.DataFrame) -> str:
    return "Index" if "Index" in orders.columns else "Fill Index"


def _order_dates(orders: pd.DataFrame) -> list[str]:
    return sorted(set(orders[_order_time_column(orders)].astype(str)))


def _orders_on(orders: pd.DataFrame, date: str) -> pd.DataFrame:
    return orders[orders[_order_time_column(orders)].astype(str) == date]


def _first_order(orders: pd.DataFrame) -> pd.Series:
    return orders.sort_values(_order_time_column(orders)).iloc[0]


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

    pf = simulate_single_book(close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly"))

    # Only the first bar and terminal-liquidation last bar produce orders;
    # the NaN rows in between do not rebalance.
    orders = pf.orders.records_readable
    assert _order_dates(orders) == ["2024-01-01", "2024-01-04"]
    # Positions persist through NaN rows.
    holdings_before_terminal = pf.assets.iloc[-2]
    assert holdings_before_terminal[(_SINGLE_CANDIDATE_ID, "A")] > 0
    assert holdings_before_terminal[(_SINGLE_CANDIDATE_ID, "B")] > 0


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

    pf = simulate_single_book(close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly"))

    assets = pf.assets
    assert assets.iloc[1].to_dict() == pytest.approx({(_SINGLE_CANDIDATE_ID, "A"): 0.0, (_SINGLE_CANDIDATE_ID, "B"): 0.0})
    orders = pf.orders.records_readable
    second_bar_orders = _orders_on(orders, "2024-01-02")
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

    pf = simulate_single_book(close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly"))

    orders = pf.orders.records_readable
    third_bar = _orders_on(orders, "2024-01-03")
    sides_by_symbol = {row["Column"]: row["Side"] for _, row in third_bar.iterrows()}
    assert sides_by_symbol == {(_SINGLE_CANDIDATE_ID, "A"): "Sell", (_SINGLE_CANDIDATE_ID, "B"): "Buy"}
    assert pf.assets.iloc[2][(_SINGLE_CANDIDATE_ID, "A")] == pytest.approx(0.0)
    assert pf.assets.iloc[2][(_SINGLE_CANDIDATE_ID, "B")] > 0


def test_symmetric_directional_band_holds_drift_inside_shared_gate() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"A": [100.0, 110.0, 110.0, 110.0]}, index=index)
    allocations = pd.DataFrame({"A": [0.5, 0.5, np.nan, np.nan]}, index=index)
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        fixed_fee=0,
        direction="longonly",
        band_up=0.03,
        band_down=0.03,
    )

    pf = simulate_single_book(close, allocations, config)

    assert _order_dates(pf.orders.records_readable) == ["2024-01-01", "2024-01-04"]
    realized_before_gate = (50.0 * 110.0) / (50.0 * 110.0 + 5_000.0)
    realized = pf.get_allocations(group_by=None).loc[index[1], (_SINGLE_CANDIDATE_ID, "A")]
    assert realized == pytest.approx(gate(realized_before_gate, 0.5, 0.03, 0.03))


def test_symmetric_directional_band_trades_drift_outside_shared_gate() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"A": [100.0, 110.0, 110.0, 110.0]}, index=index)
    allocations = pd.DataFrame({"A": [0.5, 0.5, np.nan, np.nan]}, index=index)
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        fixed_fee=0,
        direction="longonly",
        band_up=0.01,
        band_down=0.01,
    )

    pf = simulate_single_book(close, allocations, config)

    assert _order_dates(pf.orders.records_readable) == ["2024-01-01", "2024-01-02", "2024-01-04"]
    realized_before_gate = (50.0 * 110.0) / (50.0 * 110.0 + 5_000.0)
    realized = pf.get_allocations(group_by=None).loc[index[1], (_SINGLE_CANDIDATE_ID, "A")]
    assert realized == pytest.approx(gate(realized_before_gate, 0.5, 0.01, 0.01))


def test_band_breach_trades_to_interior_destination_fraction() -> None:
    """destination_fraction=0.5 stops the breach trade halfway between band edge
    and target (0.505 here) — distinct from both hold (~0.524) and target (0.5),
    so this pins the destination array reaching the compiled gate."""
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"A": [100.0, 110.0, 110.0, 110.0]}, index=index)
    allocations = pd.DataFrame({"A": [0.5, 0.5, np.nan, np.nan]}, index=index)
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        fixed_fee=0,
        direction="longonly",
        band_up=0.01,
        band_down=0.01,
        band_destination_fraction=0.5,
    )

    pf = simulate_single_book(close, allocations, config)

    realized_before_gate = (50.0 * 110.0) / (50.0 * 110.0 + 5_000.0)
    expected = gate(realized_before_gate, 0.5, 0.01, 0.01, 0.5)
    assert expected == pytest.approx(0.505)
    realized = pf.get_allocations(group_by=None).loc[index[1], (_SINGLE_CANDIDATE_ID, "A")]
    assert realized == pytest.approx(expected)


def test_symmetric_directional_band_holds_at_inclusive_boundary() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    boundary_price = 2600.0 / 24.0
    close = pd.DataFrame({"A": [100.0, boundary_price, boundary_price, boundary_price]}, index=index)
    allocations = pd.DataFrame({"A": [0.5, 0.5, np.nan, np.nan]}, index=index)
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        fixed_fee=0,
        direction="longonly",
        band_up=0.02,
        band_down=0.02,
    )

    pf = simulate_single_book(close, allocations, config)

    assert _order_dates(pf.orders.records_readable) == ["2024-01-01", "2024-01-04"]
    realized_before_gate = (50.0 * boundary_price) / (50.0 * boundary_price + 5_000.0)
    realized = pf.get_allocations(group_by=None).loc[index[1], (_SINGLE_CANDIDATE_ID, "A")]
    assert realized == pytest.approx(gate(realized_before_gate, 0.5, 0.02, 0.02))


def test_asymmetric_band_down_gates_adds_more_than_trims() -> None:
    add_pf = _simulate_drift_rebalance(second_price=90.0, band_up=0.01, band_down=0.03)
    trim_pf = _simulate_drift_rebalance(second_price=110.0, band_up=0.01, band_down=0.03)

    assert _order_dates(add_pf.orders.records_readable) == ["2024-01-01", "2024-01-04"]
    add_realized_before_gate = (50.0 * 90.0) / (50.0 * 90.0 + 5_000.0)
    add_realized = add_pf.get_allocations(group_by=None).loc[
        pd.Timestamp("2024-01-02"), (_SINGLE_CANDIDATE_ID, "A")
    ]
    assert add_realized == pytest.approx(gate(add_realized_before_gate, 0.5, 0.01, 0.03))

    assert _order_dates(trim_pf.orders.records_readable) == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-04",
    ]
    trim_realized_before_gate = (50.0 * 110.0) / (50.0 * 110.0 + 5_000.0)
    trim_realized = trim_pf.get_allocations(group_by=None).loc[
        pd.Timestamp("2024-01-02"), (_SINGLE_CANDIDATE_ID, "A")
    ]
    assert trim_realized == pytest.approx(gate(trim_realized_before_gate, 0.5, 0.01, 0.03))


def test_asymmetric_band_up_gates_trims_more_than_adds() -> None:
    add_pf = _simulate_drift_rebalance(second_price=90.0, band_up=0.03, band_down=0.01)
    trim_pf = _simulate_drift_rebalance(second_price=110.0, band_up=0.03, band_down=0.01)

    assert _order_dates(add_pf.orders.records_readable) == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-04",
    ]
    add_realized_before_gate = (50.0 * 90.0) / (50.0 * 90.0 + 5_000.0)
    add_realized = add_pf.get_allocations(group_by=None).loc[
        pd.Timestamp("2024-01-02"), (_SINGLE_CANDIDATE_ID, "A")
    ]
    assert add_realized == pytest.approx(gate(add_realized_before_gate, 0.5, 0.03, 0.01))

    assert _order_dates(trim_pf.orders.records_readable) == ["2024-01-01", "2024-01-04"]
    trim_realized_before_gate = (50.0 * 110.0) / (50.0 * 110.0 + 5_000.0)
    trim_realized = trim_pf.get_allocations(group_by=None).loc[
        pd.Timestamp("2024-01-02"), (_SINGLE_CANDIDATE_ID, "A")
    ]
    assert trim_realized == pytest.approx(gate(trim_realized_before_gate, 0.5, 0.03, 0.01))


def test_instrument_bands_gate_each_symbol_independently() -> None:
    index = pd.date_range("2024-01-01", periods=4)
    es = InstrumentId.from_str("ES.XCME")
    spy = InstrumentId.from_str("SPY.ARCA")
    close = pd.DataFrame(
        {
            es: [100.0, 110.0, 110.0, 110.0],
            spy: [100.0, 100.0, 100.0, 100.0],
        },
        index=index,
    )
    allocations = pd.DataFrame(
        {es: [0.5, 0.5, np.nan, np.nan], spy: [0.0, 0.5, np.nan, np.nan]},
        index=index,
    )
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        fixed_fee=0,
        direction="longonly",
        band_up=0.01,
        band_down=0.01,
    )
    # ES carries a wide override band; SPY is absent from the map, so it gates at the
    # sleeve-wide default (0.01) and trades the same drift ES holds.
    instrument_bands = {es: DriftBand(up=0.03, down=0.03)}

    pf = simulate_single_book(close, allocations, config, instrument_bands=instrument_bands)

    second_bar = _orders_on(pf.orders.records_readable, "2024-01-02")
    assert set(second_bar["Column"]) == {(_SINGLE_CANDIDATE_ID, spy)}
    assert set(second_bar["Side"]) == {"Buy"}
    realized_before_gate = (50.0 * 110.0) / (50.0 * 110.0 + 5_000.0)
    realized = pf.get_allocations(group_by=None).loc[
        index[1], (_SINGLE_CANDIDATE_ID, es)
    ]
    assert realized == pytest.approx(gate(realized_before_gate, 0.5, 0.03, 0.03))


def _simulate_drift_rebalance(
    *,
    second_price: float,
    band_up: float,
    band_down: float,
) -> vbt.Portfolio:
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"A": [100.0, second_price, second_price, second_price]}, index=index)
    allocations = pd.DataFrame({"A": [0.5, 0.5, np.nan, np.nan]}, index=index)
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        fixed_fee=0,
        direction="longonly",
        band_up=band_up,
        band_down=band_down,
    )
    return simulate_single_book(close, allocations, config)


def test_shortonly_drift_resizes_short_to_target_through_shared_gate() -> None:
    """A short leg traverses the gate's trade (resize) branch correctly.

    The resize branch rewrites the order as a signed target-percent with direction
    Both; a short must therefore rebalance back to its negative target, not collapse
    to zero. Price rises, so the short drifts more negative than its -0.5 target: a
    wide band holds that drift (and proves the short *entered*), a narrow band trades
    it back to -0.5.
    """
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"A": [100.0, 110.0, 110.0, 110.0]}, index=index)
    allocations = pd.DataFrame({"A": [-0.5, -0.5, np.nan, np.nan]}, index=index)

    def realized_at_drift(band: float) -> tuple[float, list[str]]:
        pf = simulate_single_book(
            close,
            allocations,
            make_portfolio_config(
                fees=0,
                slippage=0,
                fixed_fee=0,
                direction="shortonly",
                band_up=band,
                band_down=band,
            ),
        )
        realized = pf.get_allocations(group_by=None).loc[
            index[1], (_SINGLE_CANDIDATE_ID, "A")
        ]
        return realized, _order_dates(pf.orders.records_readable)

    # Wide band: enters the short at bar 0, then holds bar 1's drift. The held
    # weight is the undisturbed drift, and being < -0.5 proves the short entry
    # (a resize from flat) filled to target rather than to zero.
    drifted, held_dates = realized_at_drift(0.20)
    assert held_dates == ["2024-01-01", "2024-01-04"]
    assert drifted < -0.5

    # Narrow band: the drift is outside it, so the short resizes back to target.
    realized, traded_dates = realized_at_drift(0.01)
    assert "2024-01-02" in traded_dates
    # The resized short lands on its -0.5 target (not 0.0, the pre-fix bug, nor the
    # held drift); abs tolerance covers the engine's short-rebalance residual.
    assert realized == pytest.approx(gate(drifted, -0.5, 0.01, 0.01), abs=1e-4)
    assert realized == pytest.approx(-0.5, abs=1e-4)


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

    pf = simulate_single_book(close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly"))

    final_assets = pf.assets.iloc[-1]
    final_cash = float(pf.cash.iloc[-1])
    final_equity = float(pf.value.iloc[-1])
    assert final_assets.to_dict() == pytest.approx({(_SINGLE_CANDIDATE_ID, "A"): 0.0, (_SINGLE_CANDIDATE_ID, "B"): 0.0})
    assert final_cash == pytest.approx(final_equity)
    orders = pf.orders.records_readable
    last_bar = _orders_on(orders, "2024-01-04")
    assert set(last_bar["Side"]) == {"Sell"}
    assert set(last_bar["Column"]) == {(_SINGLE_CANDIDATE_ID, "A"), (_SINGLE_CANDIDATE_ID, "B")}


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

    pf = simulate_portfolio_batch(
        close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly"),
        periods_per_year=252,
    )

    candidate_index = pf.wrapper.grouper.get_index()
    assert list(candidate_index) == ["cand-a", "cand-b", "cand-c"]
    pf_columns = pf.wrapper.columns
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
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, np.nan, np.nan], "B": [-0.5, np.nan, np.nan, np.nan]},
        index=index,
    )

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, gross_cap=1.0, direction="both"),
    )

    assets = pf.assets
    assert assets.iloc[1][(_SINGLE_CANDIDATE_ID, "A")] > 0
    assert assets.iloc[1][(_SINGLE_CANDIDATE_ID, "B")] < 0
    realized = pf.get_allocations(group_by=False)
    assert realized.iloc[1][(_SINGLE_CANDIDATE_ID, "B")] < 0


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
    allocations.loc[index[0], ("cand-ok", "A")] = 0.5
    allocations.loc[index[0], ("cand-ok", "B")] = -0.5
    allocations.loc[index[0], ("cand-net-long", "A")] = 0.5
    allocations.loc[index[0], ("cand-net-long", "B")] = 0.5

    config = make_portfolio_config(
        fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"
    )
    with pytest.raises(ValueError, match="cand-net-long"):
        simulate_portfolio_batch(close, allocations, config, periods_per_year=252)


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
    allocations.loc[index[0], ("cand-has-short", "A")] = 0.5
    allocations.loc[index[0], ("cand-has-short", "B")] = -0.5

    config = make_portfolio_config(
        fees=0, slippage=0, gross_cap=1.0, net_cap=1.0, direction="longonly"
    )
    with pytest.raises(ValueError, match="longonly"):
        simulate_portfolio_batch(close, allocations, config, periods_per_year=252)


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
    allocations.loc[index[0], ("cand-neutral", "A")] = 0.5
    allocations.loc[index[0], ("cand-neutral", "B")] = -0.5

    config = make_portfolio_config(
        fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"
    )
    pf = simulate_portfolio_batch(close, allocations, config, periods_per_year=252)

    assert isinstance(pf, vbt.Portfolio)


def test_single_portfolio_rejects_book_breaching_gross_cap() -> None:
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"A": [10.0, 10.0, 10.0], "B": [20.0, 20.0, 20.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.8, np.nan, np.nan], "B": [0.8, np.nan, np.nan]},
        index=index,
    )

    config = make_portfolio_config(
        fees=0, slippage=0, gross_cap=1.0, net_cap=1.0, direction="longonly"
    )
    with pytest.raises(ValueError, match="gross_cap"):
        simulate_single_book(close, allocations, config)


def test_market_neutral_run_book_is_net_zero_and_realized_matches_requested() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0, 14.0], "B": [20.0, 19.0, 18.0, 17.0, 16.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [1.0, np.nan, np.nan, np.nan, np.nan], "B": [-1.0, np.nan, np.nan, np.nan, np.nan]},
        index=index,
    )

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"),
    )

    realized = pf.get_allocations(group_by=None)
    fill_row = realized.loc[index[0]]
    assert fill_row[(_SINGLE_CANDIDATE_ID, "A")] == pytest.approx(1.0, abs=2e-5)
    assert fill_row[(_SINGLE_CANDIDATE_ID, "B")] == pytest.approx(-1.0, abs=2e-5)
    assert fill_row.sum() == pytest.approx(0.0, abs=1e-9)


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

    pf = simulate_single_book(close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly"))

    assets = pf.assets
    assert (assets.iloc[1] >= 0).all()


def test_split_gap_row_is_masked_before_pfo_and_no_orders_land_on_gap_affected_row() -> None:
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

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, direction="longonly"),
        market_index=market_index,
    )

    # The allocation at split_index[2] (2024-01-04) sits after a market_index gap
    # (2024-01-03) and is masked as non-executable — no orders land on that date.
    # Terminal liquidation still fills on the last bar (2024-01-05).
    orders = pf.orders.records_readable
    order_dates = _order_dates(orders)
    assert "2024-01-04" not in order_dates
    assert "2024-01-05" in order_dates


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
        simulate_single_book(close, allocations, make_portfolio_config(direction="longonly"))


def test_portfolio_inputs_reject_index_mismatches_instead_of_dropping_rows() -> None:
    close, allocations = _two_symbol_inputs()
    allocations = allocations.iloc[:-1]

    with pytest.raises(ValueError, match="index"):
        simulate_single_book(close, allocations, make_portfolio_config(direction="longonly"))


def test_long_only_book_is_byte_for_byte_unchanged_with_carry_on_by_default() -> None:
    # ADR-0007 guarantee: a long-only book has no short legs, so the all-zero short-masked
    # cash_dividends leaves the simulation byte-for-byte identical whether carry rates are
    # the non-zero default or explicitly zero.
    close, allocations = _two_symbol_inputs()

    carry_on = simulate_single_book(
        close, allocations, make_portfolio_config(fees=0, slippage=0, direction="longonly")
    )
    carry_off = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(
            fees=0, slippage=0, direction="longonly", short_borrow_rate=0.0, short_rebate_rate=0.0
        ),
    )

    pd.testing.assert_series_equal(
        carry_on.value, carry_off.value
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

    carry_on = make_portfolio_config(fees=0, slippage=0, gross_cap=2.0, direction="both")
    carry_off = make_portfolio_config(
        fees=0,
        slippage=0,
        gross_cap=2.0,
        direction="both",
        short_borrow_rate=0.0,
        short_rebate_rate=0.0,
    )

    short_on = _total_return(simulate_single_book(close, short_book, carry_on))
    short_off = _total_return(simulate_single_book(close, short_book, carry_off))
    long_on = _total_return(simulate_single_book(close, long_only_book, carry_on))

    assert short_on < short_off
    assert short_off == pytest.approx(0.0, abs=1e-9)
    # The long-only flat book is unaffected by carry — long legs are never charged.
    assert long_on == pytest.approx(0.0, abs=1e-9)


def test_distribution_cash_dividends_places_unmasked_cash_on_ex_date() -> None:
    instrument_id = InstrumentId.from_str("DIV.SIM")
    index = pd.date_range("2024-01-01", periods=4)
    columns = pd.MultiIndex.from_tuples(
        [("candidate-a", instrument_id), ("candidate-b", instrument_id)],
        names=["candidate_id", "symbol"],
    )
    close = pd.DataFrame(100.0, index=index, columns=columns)
    distribution = Distribution.from_ex_date(
        instrument_id,
        "2024-01-03",
        amount=1.25,
        currency="USD",
    )

    cash = distribution_cash_dividends(close, [distribution])

    assert cash.loc[pd.Timestamp("2024-01-01")].tolist() == [0.0, 0.0]
    assert cash.loc[pd.Timestamp("2024-01-03")].tolist() == [1.25, 1.25]


def test_distribution_cash_dividends_converts_non_base_cash() -> None:
    instrument_id = InstrumentId.from_str("DIV.SIM")
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({instrument_id: np.full(4, 100.0)}, index=index)
    distribution = Distribution.from_ex_date(
        instrument_id,
        "2024-01-03",
        amount=2.00,
        currency="USD",
    )
    conversion = CurrencyConversion(
        {instrument_id: pd.Series([0.90, 0.95], index=index[[0, 2]])}
    )

    cash = distribution_cash_dividends(
        close,
        [distribution],
        currency_conversion=conversion,
    )

    assert cash.loc[pd.Timestamp("2024-01-03"), instrument_id] == pytest.approx(1.90)


def test_distribution_cash_increases_long_total_return() -> None:
    instrument_id = InstrumentId.from_str("DIV.SIM")
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame({instrument_id: np.full(5, 100.0)}, index=index)
    columns = pd.MultiIndex.from_tuples(
        [("candidate-a", instrument_id)],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(
        [[1.0], [np.nan], [np.nan], [np.nan], [np.nan]],
        index=index,
        columns=columns,
    )
    config = make_portfolio_config(
        fees=0,
        slippage=0,
        direction="longonly",
        short_borrow_rate=0.0,
        short_rebate_rate=0.0,
    )
    distribution = Distribution.from_ex_date(
        instrument_id,
        "2024-01-03",
        amount=1.0,
        currency="USD",
    )

    without = _total_return(
        simulate_portfolio_batch(close, allocations, config, periods_per_year=252)
    )
    with_distribution = _total_return(
        simulate_portfolio_batch(
            close,
            allocations,
            config,
            periods_per_year=252,
            distributions=[distribution],
        )
    )

    assert without == pytest.approx(0.0, abs=1e-9)
    assert with_distribution == pytest.approx(0.01, abs=1e-9)


def _total_return(pf: vbt.Portfolio) -> float:
    value = pf.get_total_return()
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)


def test_records_count_exit_trades_for_long_and_short_legs() -> None:
    # A signed book that opens a long A / short B, then flattens both: each leg produces a
    # closed (exit) trade. The portfolio must count exit trades for both the long AND short
    # legs so the short leg's realized round-trip is auditable.
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 19.0, 18.0, 17.0]},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, 0.0, np.nan], "B": [-0.5, np.nan, 0.0, np.nan]},
        index=index,
    )

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, gross_cap=1.0, direction="both"),
    )

    exit_trades = pf.exit_trades.records_readable
    assert len(exit_trades) == 2
    exit_symbols = [row["Column"] for _, row in exit_trades.iterrows()]
    assert set(exit_symbols) == {(_SINGLE_CANDIDATE_ID, "A"), (_SINGLE_CANDIDATE_ID, "B")}


def _underfilled_leverage_inputs() -> tuple[pd.DataFrame, pd.DataFrame, PortfolioConfig]:
    """Return (close, allocations, config) for a leveraged long/short book.

    Gross equals the leverage cap (5.0), then a mid-run price drift at bar 10
    forces a rebalance that stresses the cash-sharing pool.  With the surplus
    buying-power multiplier (k >= 2) the book fills cleanly; without it, the
    engine would under-fill under eager leverage.
    """
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

    config = make_portfolio_config(
        fees=0,
        slippage=0,
        gross_cap=5.0,
        net_cap=0.0,
        direction="both",
        init_cash=10000,
        short_borrow_rate=0.0,
        short_rebate_rate=0.0,
    )
    return close, allocations, config


def test_underfilled_leveraged_book_fills_cleanly_with_surplus_buying_power() -> None:
    # With surplus buying power (leverage = k x gross_cap, k >= 2), the
    # formerly under-filled leveraged book now fills exactly: zero NoCash
    # rejections, realized weights == requested at the mid-run rebalance.
    close, allocations, config = _underfilled_leverage_inputs()
    pf = simulate_portfolio_batch(close, allocations, config, periods_per_year=252)

    # No NoCash rejections in the logs.
    records = pf.logs.records
    assert records.empty or records[records["res_status_info"] == OrderStatusInfo.NoCash].empty

    # Realized allocations match requested at the bar-10 rebalance.
    realized = pf.get_allocations(group_by=None)
    fill_row = realized.loc[allocations.index[10]]
    # cand-underfilled: A/C long, B/D short at 1.25 each
    assert fill_row[("cand-underfilled", "A")] == pytest.approx(1.25, abs=1e-9)
    assert fill_row[("cand-underfilled", "B")] == pytest.approx(-1.25, abs=1e-9)
    assert fill_row[("cand-underfilled", "C")] == pytest.approx(1.25, abs=1e-9)
    assert fill_row[("cand-underfilled", "D")] == pytest.approx(-1.25, abs=1e-9)


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

    pf = simulate_portfolio_batch(
        close, allocations,
        make_portfolio_config(fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both"),
        periods_per_year=252,
    )
    assert isinstance(pf, vbt.Portfolio)


def test_batch_nocash_tripwire_is_invoked_and_error_propagates(monkeypatch) -> None:
    # The NoCash tripwire is called exactly once during simulate_portfolio_batch
    # and its ValueError propagates to the caller.
    import research.aegis_research.portfolios as portfolios_module

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
    config = make_portfolio_config(fees=0, slippage=0, gross_cap=2.0, net_cap=0.0, direction="both")

    calls = []

    def _spy_guard(pf):
        calls.append(pf)
        raise ValueError("NoCash")

    monkeypatch.setattr(portfolios_module, "_assert_no_nocash_rejection", _spy_guard)

    with pytest.raises(ValueError, match="NoCash"):
        simulate_portfolio_batch(close, allocations, config, periods_per_year=252)

    assert len(calls) == 1


def test_batch_of_one_candidate_equals_single_group_by_true() -> None:
    """Prove ExceptLevel-of-one-candidate ≡ group_by=True over plain symbols.

    The batched simulation with one candidate under ``ExceptLevel(symbol)``
    grouping collapses to one shared-cash group over all symbols, which is
    numerically identical to ``group_by=True`` on plain symbol columns.
    This is the load-bearing proof that the single-path can be deleted —
    batch-of-one produces the same book.
    """
    index = pd.date_range("2024-01-01", periods=20)
    rng = np.random.RandomState(42)
    close = pd.DataFrame(
        {
            "A": rng.randn(20).cumsum() + 100.0,
            "B": rng.randn(20).cumsum() + 200.0,
        },
        index=index,
    )
    # Exercise cash-sharing: a rebalance that must sell A to buy more B
    # on bar 10, proving the cash-sharing scope is identical.
    allocations = pd.DataFrame(
        {
            "A": [0.5] + [np.nan] * 9 + [0.2] + [np.nan] * 9,
            "B": [0.5] + [np.nan] * 9 + [0.8] + [np.nan] * 9,
        },
        index=index,
    )
    config = make_portfolio_config(fees=0, slippage=0, direction="longonly")

    pf_single = simulate_single_book(
        close, allocations, config, periods_per_year=252
    )

    columns = pd.MultiIndex.from_product(
        [[_SINGLE_CANDIDATE_ID], close.columns],
        names=["candidate_id", "symbol"],
    )
    alloc_mi = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    alloc_mi.loc[index[0], (_SINGLE_CANDIDATE_ID, "A")] = 0.5
    alloc_mi.loc[index[0], (_SINGLE_CANDIDATE_ID, "B")] = 0.5
    alloc_mi.loc[index[10], (_SINGLE_CANDIDATE_ID, "A")] = 0.2
    alloc_mi.loc[index[10], (_SINGLE_CANDIDATE_ID, "B")] = 0.8

    pf_batch = simulate_portfolio_batch(
        close, alloc_mi, config,
        periods_per_year=252,
    )

    pd.testing.assert_series_equal(pf_single.value, pf_batch.value, check_names=False)


def test_single_book_market_index_missing_row_raises() -> None:
    """When the market index does not contain a simulation row, an error propagates."""
    index = pd.date_range("2024-01-01", periods=3)
    market_index = index[[0, 2]]
    close = pd.DataFrame(
        {"A": [10.0] * 3, "B": [20.0] * 3},
        index=index,
    )
    allocations = pd.DataFrame(
        {"A": [0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5]},
        index=index,
    )

    with pytest.raises(ValueError, match="market_index"):
        simulate_single_book(
            close,
            allocations,
            make_portfolio_config(fees=0, slippage=0, direction="longonly"),
            market_index=market_index,
        )


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


def _distinct_open_close_entry_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """One symbol with open != close per bar, going 100% long at bar 0's close.

    Distinct open/close prices let the first order's fill price reveal which bar and
    which price the fill-timing resolved to: bar 0 close = 10.0, bar 1 open = 11.5,
    bar 1 close = 11.0.
    """
    index = pd.date_range("2024-01-01", periods=4)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0]}, index=index)
    open_ = pd.DataFrame({"A": [10.5, 11.5, 12.5, 13.5]}, index=index)
    allocations = pd.DataFrame({"A": [1.0, np.nan, np.nan, np.nan]}, index=index)
    return close, open_, allocations


def test_next_close_fill_timing_fills_at_next_bar_close() -> None:
    close, open_, allocations = _distinct_open_close_entry_inputs()

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, direction="longonly", fill_timing="next_close"),
        open_=open_,
    )

    first_order = _first_order(pf.orders.records_readable)
    assert first_order["Price"] == pytest.approx(11.0)  # bar 1 close, not bar 0 close or bar 1 open


def test_next_open_fill_timing_fills_at_next_bar_open() -> None:
    close, open_, allocations = _distinct_open_close_entry_inputs()

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, direction="longonly", fill_timing="next_open"),
        open_=open_,
    )

    first_order = _first_order(pf.orders.records_readable)
    assert first_order["Price"] == pytest.approx(11.5)  # bar 1 open, not bar 1 close


def test_same_close_fill_timing_fills_at_current_bar_close() -> None:
    close, _open, allocations = _distinct_open_close_entry_inputs()

    pf = simulate_single_book(
        close,
        allocations,
        make_portfolio_config(fees=0, slippage=0, direction="longonly", fill_timing="same_close"),
    )

    first_order = _first_order(pf.orders.records_readable)
    assert first_order[_order_time_column(pf.orders.records_readable)] == pd.Timestamp("2024-01-01")  # bar 0, no shift
    assert first_order["Price"] == pytest.approx(10.0)  # bar 0's own close


def test_portfolio_config_fill_timing_defaults_to_next_close() -> None:
    assert PortfolioConfig(gross_cap=1.0, direction="longonly").fill_timing == "next_close"


def test_next_open_fill_timing_without_open_prices_raises() -> None:
    close, _open, allocations = _distinct_open_close_entry_inputs()

    with pytest.raises(ValueError, match=r"next_open.*[Oo]pen"):
        simulate_single_book(
            close,
            allocations,
            make_portfolio_config(fees=0, slippage=0, direction="longonly", fill_timing="next_open"),
            # open_ omitted -> next_open cannot resolve a fill price
        )


def test_batch_exposure_gate_names_the_breaching_candidate() -> None:
    # Wiring of the kernel Exposure Validation gate: the candidate labels are derived
    # from the SYMBOL_LEVEL complement and the offender is phrased as a Candidate.
    # Gate math itself is pinned kernel-side (aegis-runtime test_exposure_validation).
    index = pd.date_range("2024-01-01", periods=2)
    close = pd.DataFrame({"A": [10.0, 10.0], "B": [20.0, 20.0]}, index=index)
    columns = pd.MultiIndex.from_tuples(
        [(candidate, symbol) for candidate in ("candidate-a", "candidate-b") for symbol in ("A", "B")],
        names=["candidate_id", "symbol"],
    )
    # candidate-a stays at gross 1.0; candidate-b breaches (Σ|wᵢ| = 1.5).
    allocations = pd.DataFrame([[0.5, 0.5, 1.0, 0.5]] * 2, index=index, columns=columns)

    with pytest.raises(ValueError, match="candidate 'candidate-b' gross exposure"):
        simulate_portfolio_batch(
            close,
            allocations,
            make_portfolio_config(direction="longonly"),
            periods_per_year=252,
        )

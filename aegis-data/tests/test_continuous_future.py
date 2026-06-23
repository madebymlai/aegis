"""Continuous-future roll-transition table (aegis-data).

``roll_transitions`` turns a dated-leg :class:`~aegis_data.chain.ContractChain` into
the explicit roll seams Nautilus materialises a back-adjusted continuous series from:
each seam names the two legs (native ``InstrumentId``) and the price gap at the roll
(each leg's Close on the roll day).  Pure — no Nautilus engine, no I/O.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.chain import ContractChain
from aegis_data.continuous_future import continuous_future, roll_transitions


def _frame(dates: list[str], close: list[float]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {"Open": close, "High": [c + 1 for c in close], "Low": [c - 1 for c in close],
         "Close": close, "Volume": [10] * len(close)},
        index=idx,
    )


def test_two_leg_chain_yields_one_transition_naming_both_legs() -> None:
    pre = _frame(["2024-03-06", "2024-03-07", "2024-03-08"], [100.0, 102.0, 103.0])
    post = _frame(["2024-03-07", "2024-03-08", "2024-03-09"], [120.0, 122.0, 123.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )

    transitions = roll_transitions(chain)

    assert len(transitions) == 1
    assert transitions[0].pre_instrument_id == InstrumentId.from_str("ESH4.XCME")
    assert transitions[0].post_instrument_id == InstrumentId.from_str("ESM4.XCME")


def test_four_leg_chain_yields_three_chained_seams() -> None:
    h = _frame(["2024-03-07", "2024-03-08"], [100.0, 101.0])
    m = _frame(["2024-03-07", "2024-06-12", "2024-06-13"], [120.0, 130.0, 131.0])
    u = _frame(["2024-06-12", "2024-09-11", "2024-09-12"], [140.0, 150.0, 151.0])
    z = _frame(["2024-09-11", "2024-09-12"], [160.0, 161.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME", "ESU4.XCME", "ESZ4.XCME"),
        roll_dates=(
            pd.Timestamp("2024-03-07"),
            pd.Timestamp("2024-06-12"),
            pd.Timestamp("2024-09-11"),
        ),
        frames=(h, m, u, z),
    )

    seams = [
        (t.pre_instrument_id.value, t.post_instrument_id.value)
        for t in roll_transitions(chain)
    ]

    assert seams == [
        ("ESH4.XCME", "ESM4.XCME"),
        ("ESM4.XCME", "ESU4.XCME"),
        ("ESU4.XCME", "ESZ4.XCME"),
    ]


def test_single_leg_chain_has_no_transitions() -> None:
    only = _frame(["2024-03-06", "2024-03-07"], [100.0, 101.0])
    chain = ContractChain(symbols=("ESH4.XCME",), roll_dates=(), frames=(only,))

    assert roll_transitions(chain) == ()


def test_transition_carries_each_legs_close_on_the_roll_day() -> None:
    pre = _frame(["2024-03-06", "2024-03-07", "2024-03-08"], [100.0, 102.0, 103.0])
    post = _frame(["2024-03-07", "2024-03-08", "2024-03-09"], [120.0, 122.0, 123.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )

    transition = roll_transitions(chain)[0]

    assert transition.pre_price == 102.0  # pre leg Close on the roll day
    assert transition.post_price == 120.0  # post leg Close on the roll day


def test_transition_time_is_the_roll_day_midnight_utc() -> None:
    pre = _frame(["2024-03-06", "2024-03-07", "2024-03-08"], [100.0, 102.0, 103.0])
    post = _frame(["2024-03-07", "2024-03-08", "2024-03-09"], [120.0, 122.0, 123.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )

    transition = roll_transitions(chain)[0]

    assert transition.transition_time_ns == pd.Timestamp("2024-03-07", tz="UTC").value


def test_as_param_is_the_nautilus_transition_row() -> None:
    pre = _frame(["2024-03-06", "2024-03-07"], [100.0, 102.0])
    post = _frame(["2024-03-07", "2024-03-08"], [120.0, 122.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )

    row = roll_transitions(chain)[0].as_param()

    assert row == {
        "transition_time_ns": pd.Timestamp("2024-03-07", tz="UTC").value,
        "pre_instrument_id": "ESH4.XCME",
        "post_instrument_id": "ESM4.XCME",
        "pre_price": "102.0",
        "post_price": "120.0",
    }


def test_continuous_future_targets_the_internally_aggregated_root_bar_type() -> None:
    pre = _frame(["2024-03-06", "2024-03-07"], [100.0, 102.0])
    post = _frame(["2024-03-07", "2024-03-08"], [120.0, 122.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )

    future = continuous_future(chain, "ES")

    assert future.target_bar_type == BarType.from_str(
        "ES.XCME-1-DAY-LAST-INTERNAL@1-DAY-EXTERNAL"
    )


def test_request_params_carry_transitions_and_backward_spread_mode() -> None:
    pre = _frame(["2024-03-06", "2024-03-07"], [100.0, 102.0])
    post = _frame(["2024-03-07", "2024-03-08"], [120.0, 122.0])
    chain = ContractChain(
        symbols=("ESH4.XCME", "ESM4.XCME"),
        roll_dates=(pd.Timestamp("2024-03-07"),),
        frames=(pre, post),
    )

    params = continuous_future(chain, "ES").request_params()

    assert (
        params["continuous_future_adjustment_mode"]
        == ContinuousFutureAdjustmentType.BACKWARD_SPREAD
    )
    assert params["continuous_future_transitions"] == [
        {
            "transition_time_ns": pd.Timestamp("2024-03-07", tz="UTC").value,
            "pre_instrument_id": "ESH4.XCME",
            "post_instrument_id": "ESM4.XCME",
            "pre_price": "102.0",
            "post_price": "120.0",
        }
    ]

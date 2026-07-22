from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.optimization.continuous_replay import replay_candidates
from research.aegis_research.optimization.portfolio_simulation import ResolvedBook
from tests.support.research.aegis_research.factories import make_portfolio_config


def _candidate_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=index)
    open_ = pd.DataFrame({"A": [10.5, 11.5, 12.5, 13.5, 14.5]}, index=index)
    columns = pd.MultiIndex.from_tuples([("candidate-a", "A")], names=["candidate_id", "symbol"])
    allocations = pd.DataFrame([1.0, 1.0, 0.0, np.nan, np.nan], index=index, columns=columns)
    return close, open_, allocations


@pytest.mark.parametrize(
    ("fill_timing", "expected_price", "expects_open"),
    [("next_close", "nextclose", False), ("next_open", "nextopen", True)],
)
def test_replay_pins_the_vbt_construction_contract(
    monkeypatch: pytest.MonkeyPatch,
    fill_timing: str,
    expected_price: str,
    expects_open: bool,
) -> None:
    close, open_, allocations = _candidate_inputs()
    optimizer_call: dict[str, Any] = {}
    portfolio_call: dict[str, Any] = {}
    real_from_filled_allocations = vbt.PFO.from_filled_allocations
    real_from_optimizer = vbt.Portfolio.from_optimizer

    def capture_optimizer(frame: pd.DataFrame, **kwargs: Any) -> Any:
        optimizer_call.update(frame=frame.copy(), **kwargs)
        return real_from_filled_allocations(frame, **kwargs)

    def capture_portfolio(*args: Any, **kwargs: Any) -> Any:
        portfolio_call.update(kwargs)
        return real_from_optimizer(*args, **kwargs)

    monkeypatch.setattr(vbt.PFO, "from_filled_allocations", capture_optimizer)
    monkeypatch.setattr(vbt.Portfolio, "from_optimizer", capture_portfolio)

    result = replay_candidates(
        close,
        allocations,
        ResolvedBook(
            make_portfolio_config(
                direction="longonly", fees=0.0, slippage=0.0, fill_timing=fill_timing
            )
        ),
        scored_start=1,
        open_=open_,
        periods_per_year=252,
    )

    assert optimizer_call["valid_only"] is True
    assert optimizer_call["nonzero_only"] is False
    assert optimizer_call["unique_only"] is False
    pd.testing.assert_frame_equal(optimizer_call["frame"], allocations)
    assert portfolio_call["pf_method"] == "from_signals"
    assert portfolio_call["size_type"] == "targetpercent"
    assert portfolio_call["direction"] == "longonly"
    assert portfolio_call["cash_sharing"] is True
    assert portfolio_call["call_seq"] == "auto"
    assert isinstance(portfolio_call["group_by"], vbt.ExceptLevel)
    assert portfolio_call["sim_start"] == 1
    assert portfolio_call["sim_end"] == len(close.index)
    assert portfolio_call["price"] == expected_price
    assert portfolio_call["from_ago"] is None
    assert ("open" in portfolio_call) is expects_open
    assert portfolio_call["save_returns"] is False
    assert portfolio_call["skip_empty"] is False
    assert result.scored_start == 1
    assert result.sim_end == len(close.index)


def test_replay_has_no_terminal_liquidation() -> None:
    close, _open, allocations = _candidate_inputs()
    allocations.iloc[1:, :] = np.nan

    result = replay_candidates(
        close,
        allocations,
        ResolvedBook(
            make_portfolio_config(
                direction="longonly", fees=0.0, slippage=0.0, fill_timing="next_close"
            )
        ),
        scored_start=1,
        periods_per_year=252,
    )

    assert result.positions.iloc[-1, 0] > 0.0
    assert result.orders["Fill Index"].tolist() == [close.index[1]]
    assert result.returns.index.equals(close.index)
    assert result.values.index.equals(close.index)


def test_replay_rejects_same_close_for_close_dependent_allocations() -> None:
    close, _open, allocations = _candidate_inputs()

    with pytest.raises(ValueError, match=r"same_close.*Close-dependent"):
        replay_candidates(
            close,
            allocations,
            ResolvedBook(make_portfolio_config(fill_timing="same_close")),
            scored_start=1,
            periods_per_year=252,
        )


def test_future_suffix_mutation_leaves_earlier_path_unchanged() -> None:
    close, _open, allocations = _candidate_inputs()
    mutated_close = close.copy()
    mutated_close.iloc[3:, 0] = [130.0, 1.0]
    book = ResolvedBook(
        make_portfolio_config(
            direction="longonly", fees=0.0, slippage=0.0, fill_timing="next_close"
        )
    )

    original = replay_candidates(
        close,
        allocations,
        book,
        scored_start=1,
        periods_per_year=252,
    )
    mutated = replay_candidates(
        mutated_close,
        allocations,
        book,
        scored_start=1,
        periods_per_year=252,
    )

    pd.testing.assert_series_equal(original.values.iloc[:3], mutated.values.iloc[:3])
    pd.testing.assert_series_equal(original.returns.iloc[:3], mutated.returns.iloc[:3])
    pd.testing.assert_frame_equal(original.positions.iloc[:3], mutated.positions.iloc[:3])
    pd.testing.assert_frame_equal(
        original.orders[original.orders["Fill Index"] < close.index[3]].reset_index(drop=True),
        mutated.orders[mutated.orders["Fill Index"] < close.index[3]].reset_index(drop=True),
    )


def test_candidate_batch_matches_sequential_continuous_paths() -> None:
    index = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=index)
    book = ResolvedBook(
        make_portfolio_config(
            direction="longonly", fees=0.001, slippage=0.0, fill_timing="next_close"
        )
    )
    batch_columns = pd.MultiIndex.from_tuples(
        [("candidate-a", "A"), ("candidate-b", "A")],
        names=["candidate_id", "symbol"],
    )
    batch_allocations = pd.DataFrame(
        [[1.0, 0.5], [1.0, 0.5], [0.0, 1.0], [np.nan, np.nan], [np.nan, np.nan]],
        index=index,
        columns=batch_columns,
    )

    batch = replay_candidates(
        close,
        batch_allocations,
        book,
        scored_start=1,
        periods_per_year=252,
    )
    sequential = {
        candidate: replay_candidates(
            close,
            batch_allocations.loc[:, [candidate]],
            book,
            scored_start=1,
            periods_per_year=252,
        )
        for candidate in ("candidate-a", "candidate-b")
    }

    for candidate, replay in sequential.items():
        pd.testing.assert_series_equal(batch.values[candidate], replay.values, check_names=False)
        pd.testing.assert_series_equal(batch.returns[candidate], replay.returns, check_names=False)
        pd.testing.assert_frame_equal(batch.positions.loc[:, [candidate]], replay.positions)
        batch_orders = batch.orders[batch.orders["Column"].map(lambda value: value[0]) == candidate]
        pd.testing.assert_series_equal(
            batch_orders["Fees"].reset_index(drop=True),
            replay.costs.reset_index(drop=True),
            check_names=False,
        )
        assert len(batch_orders) == len(replay.orders)
        assert len(
            batch.trades[batch.trades["Column"].map(lambda value: value[0]) == candidate]
        ) == len(replay.trades)

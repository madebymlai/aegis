from __future__ import annotations

from enum import Enum

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.optimization.evidence import candidate_rows_from_param_index


class StopKind(Enum):
    TRAILING = "trailing"


def test_candidate_rows_are_derived_from_vbt_param_index() -> None:
    index = pd.MultiIndex.from_tuples(
        [(14, 100, 40.0, 60.0)],
        names=["rsi_window", "ma_window", "entry_threshold", "exit_threshold"],
    )

    rows = candidate_rows_from_param_index(
        index,
        source_identity={"source": "playbook", "id": "native_rsi", "source_hash": "abc"},
        portfolio_policy={"entry_budget": 1.0},
    )

    assert len(rows) == 1
    assert rows[0]["candidate_key"].startswith("cand_")
    assert rows[0]["params"] == {
        "rsi_window": 14,
        "ma_window": 100,
        "entry_threshold": 40.0,
        "exit_threshold": 60.0,
    }
    assert rows[0]["coordinates"] == {}
    assert rows[0]["identity"]["source_identity"]["source_hash"] == "abc"
    assert rows[0]["identity"]["portfolio_policy"] == {"entry_budget": 1.0}


def test_candidate_key_excludes_split_set_symbol_coordinates() -> None:
    index = pd.MultiIndex.from_tuples(
        [
            (0, "selection", "BTC", 14),
            (0, "held_out", "BTC", 14),
            (1, "selection", "ETH", 14),
        ],
        names=["split", "set", "symbol", "rsi_window"],
    )

    rows = candidate_rows_from_param_index(index, source_identity={"source_hash": "abc"})

    assert {row["candidate_key"] for row in rows} == {rows[0]["candidate_key"]}
    assert rows[0]["params"] == {"rsi_window": 14}
    assert rows[0]["coordinates"] == {"split": 0, "set": "selection", "symbol": "BTC"}
    assert rows[1]["coordinates"] == {"split": 0, "set": "held_out", "symbol": "BTC"}
    assert rows[2]["coordinates"] == {"split": 1, "set": "selection", "symbol": "ETH"}


def test_candidate_values_are_serialized_deterministically() -> None:
    index = pd.MultiIndex.from_tuples(
        [(float("nan"), None, StopKind.TRAILING, (1, 2))],
        names=["sl_stop", "tp_stop", "stop_kind", "array_param"],
    )

    rows = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        hidden_params={"no_stop_value": None},
    )

    assert rows[0]["params"] == {
        "sl_stop": {"kind": "nan"},
        "tp_stop": {"kind": "nan"},
        "stop_kind": {
            "kind": "enum",
            "type": f"{StopKind.__module__}.{StopKind.__qualname__}",
            "name": "TRAILING",
            "value": "trailing",
        },
        "array_param": [1, 2],
    }
    assert rows[0]["identity"]["hidden_params"] == {"no_stop_value": None}


def test_candidate_key_includes_hidden_source_and_portfolio_identity() -> None:
    index = pd.MultiIndex.from_tuples([(14,)], names=["rsi_window"])

    base = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        hidden_params={"hidden_threshold": 1},
        portfolio_policy={"fees": 0.001},
    )[0]
    different_hidden = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        hidden_params={"hidden_threshold": 2},
        portfolio_policy={"fees": 0.001},
    )[0]
    different_source = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "def"},
        hidden_params={"hidden_threshold": 1},
        portfolio_policy={"fees": 0.001},
    )[0]
    different_portfolio = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        hidden_params={"hidden_threshold": 1},
        portfolio_policy={"fees": 0.002},
    )[0]

    assert base["candidate_key"] != different_hidden["candidate_key"]
    assert base["candidate_key"] != different_source["candidate_key"]
    assert base["candidate_key"] != different_portfolio["candidate_key"]


def test_random_subset_rows_persist_actual_vbt_sampled_index() -> None:
    @vbt.parameterized(merge_func="concat")
    def score(a: int, b: int, c: bool) -> float:
        return float(a + b + int(c))

    sampled = score(
        a=vbt.Param([1, 2, 3]),
        b=vbt.Param([10, 20]),
        c=vbt.Param([False, True]),
        _random_subset=5,
        _seed=42,
    )

    rows = candidate_rows_from_param_index(sampled.index, source_identity={"source_hash": "abc"})

    assert [row["params"] for row in rows] == [
        {"a": 1, "b": 10, "c": False},
        {"a": 2, "b": 10, "c": False},
        {"a": 2, "b": 10, "c": True},
        {"a": 2, "b": 20, "c": False},
        {"a": 3, "b": 10, "c": True},
    ]

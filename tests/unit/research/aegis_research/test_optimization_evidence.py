from __future__ import annotations

from enum import Enum

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.optimization.evidence import (
    candidate_rows_from_param_index,
    canonical_params_key,
)

DATA_IDENTITY = {
    "source": "synthetic",
    "symbols": ["SYN"],
    "timeframe": "1D",
    "index_start": "2026-01-01",
    "index_end": "2026-01-31",
}


class StopKind(Enum):
    TRAILING = "trailing"


def test_candidate_rows_are_derived_from_vbt_param_index() -> None:
    index = pd.MultiIndex.from_tuples(
        [(14, 100, 40.0, 60.0)],
        names=["rsi_window", "ma_window", "entry_threshold", "exit_threshold"],
    )

    rows = candidate_rows_from_param_index(
        index,
        source_identity={"source": "component", "id": "native_rsi", "source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        portfolio_policy={"target_exposure_cap": 1.0},
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
    assert rows[0]["identity"]["data_identity"] == DATA_IDENTITY
    assert rows[0]["identity"]["portfolio_policy"] == {"target_exposure_cap": 1.0}


def test_candidate_key_excludes_split_set_symbol_coordinates() -> None:
    index = pd.MultiIndex.from_tuples(
        [
            (0, "selection", "BTC", 14),
            (0, "held_out", "BTC", 14),
            (1, "selection", "ETH", 14),
        ],
        names=["split", "set", "symbol", "rsi_window"],
    )

    rows = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

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
        data_identity=DATA_IDENTITY,
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


def test_canonical_params_key_matches_candidate_row_param_canonicalization() -> None:
    params = {"sl_stop": float("nan"), "array_param": (1, 2), "stop_kind": StopKind.TRAILING}
    index = pd.MultiIndex.from_tuples(
        [(float("nan"), (1, 2), StopKind.TRAILING)],
        names=["sl_stop", "array_param", "stop_kind"],
    )

    rows = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

    assert canonical_params_key(params) == canonical_params_key(rows[0]["params"])


def test_candidate_key_includes_hidden_source_and_portfolio_identity() -> None:
    index = pd.MultiIndex.from_tuples([(14,)], names=["rsi_window"])

    base = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        portfolio_policy={"fees": 0.001},
    )[0]
    different_hidden = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 2},
        portfolio_policy={"fees": 0.001},
    )[0]
    different_source = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "def"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        portfolio_policy={"fees": 0.001},
    )[0]
    different_portfolio = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        portfolio_policy={"fees": 0.002},
    )[0]

    assert base["candidate_key"] != different_hidden["candidate_key"]
    assert base["candidate_key"] != different_source["candidate_key"]
    assert base["candidate_key"] != different_portfolio["candidate_key"]


def test_candidate_key_includes_data_identity_and_carries_store_namespace() -> None:
    index = pd.MultiIndex.from_tuples([(14,)], names=["rsi_window"])

    base = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )[0]
    different_data = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity={**DATA_IDENTITY, "symbols": ["ALT"]},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )[0]
    different_store = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        store_namespace={"kind": "local_sqlite", "name": "other"},
    )[0]

    assert base["candidate_key"] != different_data["candidate_key"]
    assert base["candidate_key"] == different_store["candidate_key"]
    assert base["store_namespace"] == {"kind": "local_sqlite", "name": "default"}
    assert different_store["store_namespace"] == {"kind": "local_sqlite", "name": "other"}


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

    rows = candidate_rows_from_param_index(
        sampled.index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

    assert [row["params"] for row in rows] == [
        {"a": 1, "b": 10, "c": False},
        {"a": 2, "b": 10, "c": False},
        {"a": 2, "b": 10, "c": True},
        {"a": 2, "b": 20, "c": False},
        {"a": 3, "b": 10, "c": True},
    ]

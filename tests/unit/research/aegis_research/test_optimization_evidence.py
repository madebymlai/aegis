from __future__ import annotations

from enum import Enum

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.optimization.evidence import (
    HELD_OUT_GAP_WARNING_THRESHOLD,
    candidate_held_out_headline,
    candidate_rows_from_param_index,
    candidate_rows_from_result,
    canonical_params_key,
    held_out_warning,
    result_evidence,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
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


def _evaluated(params: dict[str, object], score: float) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        params=params,
        score=score,
        selection_metrics={0: {"total_return": score}, 1: {"total_return": score + 0.1}},
        metrics={"total_return": score + 0.05},
        held_out_metrics={0: {"total_return": score - 0.02}, 1: {"total_return": score - 0.01}},
    )


def test_candidate_rows_from_result_emits_three_role_tagged_rows() -> None:
    result = OptimizationResult(
        best=_evaluated({"rsi_window": 14}, 0.9),
        median=_evaluated({"rsi_window": 20}, 0.5),
        worst=_evaluated({"rsi_window": 5}, 0.1),
    )

    rows = candidate_rows_from_result(
        result,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        portfolio_policy={"fees": 0.001},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )

    assert [row["role"] for row in rows] == ["best", "median", "worst"]
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert {row["candidate_key"] for row in rows} == {row["candidate_key"] for row in rows}
    assert len({row["candidate_key"] for row in rows}) == 3
    best = rows[0]
    assert best["params"] == {"rsi_window": 14}
    assert best["score"] == 0.9
    assert best["selection_metrics"] == {
        "0": {"total_return": 0.9},
        "1": {"total_return": 1.0},
    }
    assert best["held_out_metrics"]["0"]["total_return"] == pytest.approx(0.88)
    assert best["metrics"] == pytest.approx({"total_return": 0.95})
    # held-out aggregate is as prominent as the in-sample aggregate (`metrics`),
    # and uses the same mean-across-splits aggregation (here (0.88 + 0.89) / 2).
    assert best["held_out_metrics_mean"] == pytest.approx({"total_return": 0.885})
    assert best["store_namespace"] == {"kind": "local_sqlite", "name": "default"}


def test_candidate_rows_from_result_shares_key_when_one_candidate_fills_all_roles() -> None:
    only = _evaluated({"rsi_window": 14}, 0.7)
    result = OptimizationResult(best=only, median=only, worst=only)

    rows = candidate_rows_from_result(
        result,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

    assert [row["role"] for row in rows] == ["best", "median", "worst"]
    assert len({row["candidate_key"] for row in rows}) == 1


def test_candidate_rows_from_result_key_matches_param_index_identity() -> None:
    result = OptimizationResult(
        best=_evaluated({"rsi_window": 14}, 0.9),
        median=_evaluated({"rsi_window": 14}, 0.9),
        worst=_evaluated({"rsi_window": 14}, 0.9),
    )
    index = pd.MultiIndex.from_tuples([(14,)], names=["rsi_window"])

    from_result = candidate_rows_from_result(
        result,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        portfolio_policy={"fees": 0.001},
    )[0]
    from_index = candidate_rows_from_param_index(
        index,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        portfolio_policy={"fees": 0.001},
    )[0]

    assert from_result["candidate_key"] == from_index["candidate_key"]


def test_candidate_rows_from_result_nan_score_becomes_none() -> None:
    blank = EvaluatedCandidate(
        params={"rsi_window": 5},
        score=float("nan"),
        selection_metrics={0: {"total_return": None}},
        metrics={"total_return": None},
        held_out_metrics={0: {"total_return": None}},
    )
    result = OptimizationResult(
        best=_evaluated({"rsi_window": 14}, 0.9),
        median=_evaluated({"rsi_window": 20}, 0.5),
        worst=blank,
    )

    rows = candidate_rows_from_result(
        result,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

    assert rows[2]["score"] is None
    assert rows[2]["metrics"] == {"total_return": None}


def test_result_evidence_serializes_three_candidates() -> None:
    result = OptimizationResult(
        best=_evaluated({"rsi_window": 14}, 0.9),
        median=_evaluated({"rsi_window": 20}, 0.5),
        worst=_evaluated({"rsi_window": 5}, 0.1),
    )

    evidence = result_evidence(result)

    assert set(evidence) == {"schema_version", "best", "median", "worst"}
    assert evidence["schema_version"] == "optimization_result.v2"
    assert evidence["best"]["params"] == {"rsi_window": 14}
    assert evidence["best"]["score"] == 0.9
    assert evidence["best"]["held_out_metrics_mean"] == pytest.approx({"total_return": 0.885})
    assert evidence["worst"]["selection_metrics"] == {
        "0": {"total_return": 0.1},
        "1": {"total_return": 0.2},
    }


def test_candidate_held_out_headline_leads_with_held_out_and_gap() -> None:
    rows = candidate_rows_from_result(
        OptimizationResult(
            best=_evaluated({"rsi_window": 14}, 0.9),
            median=_evaluated({"rsi_window": 20}, 0.5),
            worst=_evaluated({"rsi_window": 5}, 0.1),
        ),
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

    headline = candidate_held_out_headline(rows[0], metric="total_return")

    assert headline["metric"] == "total_return"
    # held-out is the unbiased headline; selection is the in-sample (optimistic) value.
    assert headline["held_out"] == pytest.approx(0.885)
    assert headline["selection"] == pytest.approx(0.95)
    assert headline["gap"] == pytest.approx(0.95 - 0.885)


def test_candidate_held_out_headline_missing_metric_is_none() -> None:
    rows = candidate_rows_from_result(
        OptimizationResult(
            best=_evaluated({"rsi_window": 14}, 0.9),
            median=_evaluated({"rsi_window": 20}, 0.5),
            worst=_evaluated({"rsi_window": 5}, 0.1),
        ),
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
    )

    headline = candidate_held_out_headline(rows[0], metric="sharpe_ratio")

    assert headline == {
        "metric": "sharpe_ratio",
        "held_out": None,
        "selection": None,
        "gap": None,
    }


def test_held_out_warning_fires_when_best_collapses_out_of_sample() -> None:
    warning = held_out_warning(
        {"metric": "sharpe_ratio", "held_out": -0.05, "selection": 1.97, "gap": 2.02}
    )

    assert warning is not None
    assert "sharpe_ratio" in warning
    assert "selection-set optimism" in warning


def test_held_out_warning_fires_when_gap_exceeds_threshold_despite_positive_held_out() -> None:
    headline = {
        "metric": "sharpe_ratio",
        "held_out": 0.2,
        "selection": 0.2 + HELD_OUT_GAP_WARNING_THRESHOLD,
        "gap": HELD_OUT_GAP_WARNING_THRESHOLD,
    }

    assert held_out_warning(headline) is not None


def test_held_out_warning_silent_when_held_out_holds_up() -> None:
    headline = {"metric": "sharpe_ratio", "held_out": 1.5, "selection": 1.6, "gap": 0.1}

    assert held_out_warning(headline) is None


def test_held_out_warning_silent_without_held_out_data() -> None:
    headline = {"metric": "sharpe_ratio", "held_out": None, "selection": 1.6, "gap": None}

    assert held_out_warning(headline) is None

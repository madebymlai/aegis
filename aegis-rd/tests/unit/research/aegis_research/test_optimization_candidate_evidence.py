from __future__ import annotations

from enum import Enum
from typing import Any

import pytest

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.optimization.candidate_evidence import (
    HELD_OUT_GAP_WARNING_THRESHOLD,
    candidate_held_out_headline,
    candidate_rows_from_result,
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


def _single_candidate_row(params: dict[str, Any], **identity_kwargs: Any) -> dict[str, Any]:
    only = _evaluated(params, 0.7)
    return candidate_rows_from_result(
        OptimizationResult(best=only, median=only, worst=only),
        **identity_kwargs,
    )[0]


def test_candidate_values_are_serialized_deterministically() -> None:
    row = _single_candidate_row(
        {
            "sl_stop": float("nan"),
            "tp_stop": None,
            "stop_kind": StopKind.TRAILING,
            "array_param": (1, 2),
        },
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"no_stop_value": None},
    )

    assert row["params"] == {
        "sl_stop": {"kind": "nan"},
        "tp_stop": None,
        "stop_kind": {
            "kind": "enum",
            "type": f"{StopKind.__module__}.{StopKind.__qualname__}",
            "name": "TRAILING",
            "value": "trailing",
        },
        "array_param": [1, 2],
    }
    assert row["identity"]["hidden_params"] == {"no_stop_value": None}


def test_candidate_key_includes_hidden_source_and_allocation_identity() -> None:
    params = {"rsi_window": 14}

    base = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        allocation_policy={"fees": 0.001},
    )
    different_hidden = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 2},
        allocation_policy={"fees": 0.001},
    )
    different_source = _single_candidate_row(
        params,
        source_identity={"source_hash": "def"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        allocation_policy={"fees": 0.001},
    )
    different_policy = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        allocation_policy={"fees": 0.002},
    )

    assert base["candidate_key"] != different_hidden["candidate_key"]
    assert base["candidate_key"] != different_source["candidate_key"]
    assert base["candidate_key"] != different_policy["candidate_key"]


def test_candidate_identity_golden_bytes_pin() -> None:
    row = _single_candidate_row(
        {"rsi_window": 14, "ma_window": 100, "entry": 40.0},
        source_identity={"source": "component", "id": "demo.rsi", "source_hash": "abc123"},
        data_identity={
            "schema_version": "candidate_data_identity.v2",
            "source": "synthetic",
            "requested_symbols": ["SYN", "ALT"],
            "symbols": ["SYN", "ALT"],
            "timeframe": "1D",
            "effective_arrays": ["Close", "Open"],
            "loaded_arrays": ["Close"],
            "rows": 31,
            "index_start": "2026-01-01",
            "index_end": "2026-01-31",
            "index_evidence": {},
            "source_metadata": {},
            "array_contract": {
                "configured_arrays": ["Close"],
                "component_required_arrays": [],
                "pipeline_required_arrays": ["Close", "Open"],
                "contract_required_arrays": ["Close", "Open"],
                "missing_required_arrays": ["Open"],
            },
        },
        hidden_params={"execution": "next_open"},
        allocation_policy={"fees": 0.001, "target_exposure_cap": 1.0},
    )

    assert canonical_json_bytes(row["identity"]) == (
        b'{"allocation_policy":{"fees":0.001,"target_exposure_cap":1.0},'
        b'"data_identity":{"array_contract":{"component_required_arrays":[],'
        b'"configured_arrays":["Close"],"contract_required_arrays":["Close","Open"],'
        b'"missing_required_arrays":["Open"],"pipeline_required_arrays":["Close","Open"]},'
        b'"effective_arrays":["Close","Open"],"index_end":"2026-01-31",'
        b'"index_evidence":{},"index_start":"2026-01-01","loaded_arrays":["Close"],'
        b'"requested_symbols":["SYN","ALT"],"rows":31,'
        b'"schema_version":"candidate_data_identity.v2",'
        b'"source":"synthetic","source_metadata":{},"symbols":["SYN","ALT"],'
        b'"timeframe":"1D"},"hidden_params":{"execution":"next_open"},"params":{"entry":40.0,'
        b'"ma_window":100,"rsi_window":14},"schema_version":"candidate_identity.v3",'
        b'"source_identity":{"id":"demo.rsi","source":"component","source_hash":"abc123"}}'
    )
    assert row["candidate_key"] == "cand_513714c16125b81fe4bf8e878311b840"


def test_candidate_key_includes_data_identity_and_carries_store_namespace() -> None:
    params = {"rsi_window": 14}

    base = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    different_data = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity={**DATA_IDENTITY, "symbols": ["ALT"]},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    different_store = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        store_namespace={"kind": "local_sqlite", "name": "other"},
    )

    assert base["candidate_key"] != different_data["candidate_key"]
    assert base["candidate_key"] == different_store["candidate_key"]
    assert base["store_namespace"] == {"kind": "local_sqlite", "name": "default"}
    assert different_store["store_namespace"] == {"kind": "local_sqlite", "name": "other"}


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
        allocation_policy={"fees": 0.001},
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
        total_candidates=12,
        excluded_degenerate=4,
        excluded_invalid=1,
    )

    evidence = result_evidence(result)

    assert set(evidence) == {
        "schema_version",
        "best",
        "median",
        "worst",
        "total",
        "excluded_invalid",
        "excluded_degenerate",
        "non_executable_rows",
    }
    assert evidence["schema_version"] == "optimization_result.v3"
    assert evidence["total"] == 12
    assert evidence["excluded_invalid"] == 1
    assert evidence["excluded_degenerate"] == 4
    assert evidence["non_executable_rows"] == 0
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

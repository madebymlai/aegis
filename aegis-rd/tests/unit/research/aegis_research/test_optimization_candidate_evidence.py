from __future__ import annotations

import hashlib
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
    separability_warning,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from tests.support.research.aegis_research.factories import make_selection_identity

DATA_IDENTITY = {
    "schema_version": "candidate_data_identity.v3",
    "requested_instrument_ids": ["SYN.XNAS"],
    "instrument_ids": ["SYN.XNAS"],
    "timeframe": "1D",
    "index_start": "2026-01-01",
    "index_end": "2026-01-31",
}


class StopKind(Enum):
    TRAILING = "trailing"


def _single_candidate_row(params: dict[str, Any], **identity_kwargs: Any) -> dict[str, Any]:
    only = _evaluated(params, 0.7)
    identity_kwargs.setdefault("selection_identity", make_selection_identity())
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
        selection_identity=make_selection_identity(),
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
        selection_identity=make_selection_identity(),
        hidden_params={"hidden_threshold": 1},
        book_settings={"fees": 0.001},
    )
    different_hidden = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        selection_identity=make_selection_identity(),
        hidden_params={"hidden_threshold": 2},
        book_settings={"fees": 0.001},
    )
    different_source = _single_candidate_row(
        params,
        source_identity={"source_hash": "def"},
        data_identity=DATA_IDENTITY,
        hidden_params={"hidden_threshold": 1},
        book_settings={"fees": 0.001},
    )
    different_policy = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        selection_identity=make_selection_identity(),
        hidden_params={"hidden_threshold": 1},
        book_settings={"fees": 0.002},
    )

    assert base["candidate_key"] != different_hidden["candidate_key"]
    assert base["candidate_key"] != different_source["candidate_key"]
    assert base["candidate_key"] != different_policy["candidate_key"]


def test_candidate_identity_golden_bytes_pin() -> None:
    row = _single_candidate_row(
        {"rsi_window": 14, "ma_window": 100, "entry": 40.0},
        source_identity={"source": "component", "id": "demo.rsi", "source_hash": "abc123"},
        data_identity={
            "schema_version": "candidate_data_identity.v3",
            "adjustment_mode": "backward_ratio",
            "requested_instrument_ids": ["SYN.XNAS", "ALT.XNAS"],
            "instrument_ids": ["SYN.XNAS", "ALT.XNAS"],
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
        book_settings={"fees": 0.001, "target_exposure_cap": 1.0},
    )

    assert hashlib.sha256(canonical_json_bytes(row["identity"])).hexdigest() == (
        "bad193abbd687a40afdedfdbd3dd0c6e0db66b9b0c74d8898db9ddb015c19136"
    )
    assert row["candidate_key"] == "cand_bad193abbd687a40afdedfdbd3dd0c6e"


def test_otherwise_identical_ratio_and_spread_runs_have_different_candidate_keys() -> None:
    params = {"rsi_window": 14}

    ratio = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity={**DATA_IDENTITY, "adjustment_mode": "backward_ratio"},
    )
    spread = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity={**DATA_IDENTITY, "adjustment_mode": "backward_spread"},
    )

    assert ratio["candidate_key"] != spread["candidate_key"]


def test_candidate_key_includes_data_identity_and_carries_store_namespace() -> None:
    params = {"rsi_window": 14}

    base = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        selection_identity=make_selection_identity(),
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    different_data = _single_candidate_row(
        params,
        source_identity={"source_hash": "abc"},
        data_identity={
            **DATA_IDENTITY,
            "requested_instrument_ids": ["ALT.XNAS"],
            "instrument_ids": ["ALT.XNAS"],
        },
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
        selection_identity=make_selection_identity(),
        book_settings={"fees": 0.001},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )

    assert [row["role"] for row in rows] == ["best", "median", "worst"]
    assert [row["ordinal_rank"] for row in rows] == [1, 2, 3]
    assert {row["candidate_key"] for row in rows} == {row["candidate_key"] for row in rows}
    assert len({row["candidate_key"] for row in rows}) == 3
    best = rows[0]
    assert best["params"] == {"rsi_window": 14}
    assert best["mean_rank"] == 0.9
    assert best["observation_block_metrics"] == {
        "0": {"total_return": 0.9},
        "1": {"total_return": 1.0},
    }
    assert best["complete_period_metrics"] == pytest.approx({"total_return": 0.95})
    assert "held_out_metrics" not in best
    assert best["store_namespace"] == {"kind": "local_sqlite", "name": "default"}


def test_candidate_rows_from_result_shares_key_when_one_candidate_fills_all_roles() -> None:
    only = _evaluated({"rsi_window": 14}, 0.7)
    result = OptimizationResult(best=only, median=only, worst=only)

    rows = candidate_rows_from_result(
        result,
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        selection_identity=make_selection_identity(),
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
        selection_identity=make_selection_identity(),
    )

    assert rows[2]["mean_rank"] is None
    assert rows[2]["complete_period_metrics"] == {"total_return": None}


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
        "omnibus",
    }
    assert evidence["schema_version"] == "optimization_result.v4"
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
    headline = candidate_held_out_headline(
        {
            "metrics": {"total_return": 0.95},
            "held_out_metrics_mean": {"total_return": 0.885},
        },
        metric="total_return",
    )

    assert headline["metric"] == "total_return"
    # held-out is the unbiased headline; selection is the in-sample (optimistic) value.
    assert headline["held_out"] == pytest.approx(0.885)
    assert headline["selection"] == pytest.approx(0.95)
    assert headline["gap"] == pytest.approx(0.95 - 0.885)


def test_candidate_held_out_headline_missing_metric_is_none() -> None:
    headline = candidate_held_out_headline({}, metric="sharpe_ratio")

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


def test_separability_warning_fires_when_field_is_indistinguishable() -> None:
    # Tiny chi-square over 12 candidates x 6 folds -> Iman-Davenport p ~ 1 -> not
    # separable -> warns, qualitatively and with a hedged (not gated) p.
    warning = separability_warning({"chi_square": 0.5, "n_candidates": 12, "n_splits": 6})

    assert warning is not None
    assert "statistically indistinguishable" in warning
    assert "lower bound" in warning


def test_separability_warning_silent_when_field_is_separable() -> None:
    # Large chi-square -> low p -> the field is separable -> no warning.
    assert separability_warning({"chi_square": 40.0, "n_candidates": 12, "n_splits": 6}) is None


def test_separability_warning_none_without_a_test() -> None:
    assert separability_warning(None) is None
    assert separability_warning({"chi_square": 5.0, "n_candidates": 1, "n_splits": 6}) is None
    assert separability_warning({"chi_square": 5.0, "n_candidates": 5, "n_splits": 1}) is None

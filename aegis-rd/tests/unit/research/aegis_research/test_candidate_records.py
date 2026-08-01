from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

import pytest

from research.aegis_research.candidates.records import (
    candidate_rows_from_result,
)
from research.aegis_research.canonical_json import canonical_json_bytes
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


def _evaluated(params: dict[str, object], score: float) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        params=params,
        score=score,
        observation_block_metrics={
            "block-000": {"total_return": score},
            "block-001": {"total_return": score + 0.1},
        },
        metrics={"total_return": score + 0.05},
    )


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


def test_candidate_key_covers_source_data_hidden_book_and_selection_identity() -> None:
    common = {
        "source_identity": {"source_hash": "abc"},
        "data_identity": DATA_IDENTITY,
        "selection_identity": make_selection_identity(),
        "hidden_params": {"hidden_threshold": 1},
        "book_settings": {"fees": 0.001},
    }
    base = _single_candidate_row({"rsi_window": 14}, **common)

    variants = []
    for field, value in (
        ("source_identity", {"source_hash": "def"}),
        ("data_identity", {**DATA_IDENTITY, "instrument_ids": ["ALT.XNAS"]}),
        ("hidden_params", {"hidden_threshold": 2}),
        ("book_settings", {"fees": 0.002}),
        ("selection_identity", make_selection_identity(ranking={"metric": "other"})),
    ):
        changed = dict(common)
        changed[field] = value
        variants.append(_single_candidate_row({"rsi_window": 14}, **changed))

    assert all(row["candidate_key"] != base["candidate_key"] for row in variants)


def test_candidate_identity_golden_bytes_pin() -> None:
    row = _single_candidate_row(
        {"rsi_window": 14, "ma_window": 100, "entry": 40.0},
        source_identity={
            "source": "component",
            "id": "demo.rsi",
            "source_hash": "abc123",
        },
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
        "cc5b9d6f370dfd5ebe82314fb5160d1c7a462bddb9e74ff2e34f75784905d8c7"
    )
    assert row["candidate_key"] == "cand_cc5b9d6f370dfd5ebe82314fb5160d1c"


def test_candidate_rows_publish_only_observation_block_and_complete_period_metrics() -> None:
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
    )

    assert [row["role"] for row in rows] == ["best", "median", "worst"]
    assert [row["ordinal_rank"] for row in rows] == [1, 2, 3]
    assert len({row["candidate_key"] for row in rows}) == 3
    assert rows[0]["observation_block_metrics"] == {
        "block-000": {"total_return": 0.9},
        "block-001": {"total_return": 1.0},
    }
    assert rows[0]["complete_period_metrics"] == pytest.approx({"total_return": 0.95})
    assert "selection_metrics" not in rows[0]
    assert "held_out_metrics" not in rows[0]


def test_single_candidate_shares_identity_across_all_roles() -> None:
    candidate = _evaluated({"rsi_window": 14}, 0.7)
    rows = candidate_rows_from_result(
        OptimizationResult(best=candidate, median=candidate, worst=candidate),
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        selection_identity=make_selection_identity(),
    )

    assert len({row["candidate_key"] for row in rows}) == 1


def test_nan_mean_rank_and_metric_are_published_as_none() -> None:
    candidate = EvaluatedCandidate(
        params={"rsi_window": 5},
        score=float("nan"),
        observation_block_metrics={"block-000": {"total_return": None}},
        metrics={"total_return": None},
    )
    rows = candidate_rows_from_result(
        OptimizationResult(best=candidate, median=candidate, worst=candidate),
        source_identity={"source_hash": "abc"},
        data_identity=DATA_IDENTITY,
        selection_identity=make_selection_identity(),
    )

    assert rows[0]["mean_rank"] is None
    assert rows[0]["complete_period_metrics"] == {"total_return": None}

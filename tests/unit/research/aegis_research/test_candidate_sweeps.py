"""Legacy candidate-sweep contract coverage (playbook_sweep_result.v1).

These tests cover the non-optimization sweep path that remains for configs
without an `optimization` block. The forward VBT-native optimization path
(#31, aegis.optimization_source.v1) is covered by the
``tests/unit/research/aegis_research/test_optimization_*`` suites. This file
should not be extended with new candidate-axis features; #32 owns the
deprecation/removal decisions for this contract.
"""
from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.candidate_sweeps import (
    CANDIDATE_LEVEL,
    INDICATOR_RESULT_KIND,
    PLAYBOOK_SWEEP_CONTRACT,
    STRATEGY_AXIS_KIND,
    STRATEGY_MATERIALIZER_KEY,
    STRATEGY_SIGNALS_KIND,
    SYMBOL_LEVEL,
    CandidateAxis,
    CandidateSweepError,
    SignalMaterializationRequest,
    SweepCandidate,
    candidate_id_from_params,
    compose_candidate_grid,
    composed_candidate_ids,
    materialize_strategy_sweep_signals,
    preflight_indicator_grid,
    validate_indicator_sweep_result,
    validate_strategy_sweep_axis,
    validate_strategy_sweep_plan,
    validate_strategy_sweep_signals,
)


def test_validate_indicator_sweep_result_exposes_candidate_axis() -> None:
    close = _close_frame()
    result = {
        "contract": PLAYBOOK_SWEEP_CONTRACT,
        "kind": INDICATOR_RESULT_KIND,
        "candidate_axis": [
            {"candidate_id": "ma-2", "params": {"window": 2}},
            {"candidate_id": "ma-5", "params": {}},
        ],
        "outputs": {"ma": _surface(close, ["ma-2", "ma-5"])},
        "diagnostics": {"grid": "fixture"},
    }

    validated = validate_indicator_sweep_result(result, source_id="ma_explore", close=close)

    assert validated.axis.count == 2
    assert validated.axis.candidate_ids == ("ma-2", "ma-5")
    assert validated.axis.candidates[1].params == {}
    assert validated.outputs["ma"].columns.names == [CANDIDATE_LEVEL, SYMBOL_LEVEL]
    assert validated.diagnostics == {"grid": "fixture"}


def test_validate_strategy_sweep_axis_and_requested_signal_batch() -> None:
    close = _close_frame()
    axis = validate_strategy_sweep_axis(
        {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_AXIS_KIND,
            "candidate_axis": [
                {"candidate_id": "fast", "params": {}},
                {"candidate_id": "slow-0.01", "params": {"threshold": 0.01}},
            ],
        },
        source_id="ma_cross",
    )
    result = {
        "contract": PLAYBOOK_SWEEP_CONTRACT,
        "kind": STRATEGY_SIGNALS_KIND,
        "entries": _surface(close, ["fast"], value=True),
        "exits": _surface(close, ["fast"], value=False),
    }

    signals = validate_strategy_sweep_signals(
        result,
        source_id="ma_cross",
        expected_candidate_ids=["fast"],
        close=close,
    )

    assert axis.candidate_ids == ("fast", "slow-0.01")
    assert signals.entries.dtypes.tolist() == [bool, bool]
    assert signals.entries.columns.get_level_values(CANDIDATE_LEVEL).unique().tolist() == ["fast"]


def test_validate_strategy_sweep_plan_materializes_requested_candidate_range() -> None:
    close = _close_frame()
    observed_requests: list[tuple[str, ...]] = []

    def materialize(request: SignalMaterializationRequest):
        observed_requests.append(request.candidate_ids)
        return {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_SIGNALS_KIND,
            "entries": _surface(close, list(request.candidate_ids), value=True),
            "exits": _surface(close, list(request.candidate_ids), value=False),
        }

    plan = validate_strategy_sweep_plan(
        {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_AXIS_KIND,
            "candidate_axis": [
                {"candidate_id": "fast", "params": {}},
                {"candidate_id": "slow-0.01", "params": {"threshold": 0.01}},
            ],
            STRATEGY_MATERIALIZER_KEY: materialize,
            "diagnostics": {"grid": "thresholds"},
        },
        source_id="ma_cross",
    )

    signals = materialize_strategy_sweep_signals(
        plan,
        source_id="ma_cross",
        requested_candidate_ids=["slow-0.01"],
        close=close,
    )

    assert plan.axis.candidate_ids == ("fast", "slow-0.01")
    assert plan.diagnostics == {"grid": "thresholds"}
    assert observed_requests == [("slow-0.01",)]
    assert signals.entries.columns.get_level_values(CANDIDATE_LEVEL).unique().tolist() == [
        "slow-0.01"
    ]


def test_strategy_sweep_request_carries_composed_candidate_context() -> None:
    close = _close_frame()
    indicator_axis = CandidateAxis(
        source="playbook",
        source_id="ma_explore",
        candidates=(SweepCandidate(candidate_id="ma-20", params={"window": 20}),),
    )
    observed_requests = []

    def materialize(request: SignalMaterializationRequest):
        observed_requests.append(request.candidates)
        return {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_SIGNALS_KIND,
            "entries": _surface(close, list(request.candidate_ids), value=True),
            "exits": _surface(close, list(request.candidate_ids), value=False),
        }

    plan = validate_strategy_sweep_plan(
        {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_AXIS_KIND,
            "candidate_axis": [{"candidate_id": "fast-0.01", "params": {"threshold": 0.01}}],
            STRATEGY_MATERIALIZER_KEY: materialize,
        },
        source_id="ma_cross",
    )
    composed_id = "strategy:playbook:ma_cross:fast-0.01+indicators:[playbook:ma_explore:ma-20]"

    materialize_strategy_sweep_signals(
        plan,
        source_id="ma_cross",
        requested_candidate_ids=[composed_id],
        indicator_axes=[indicator_axis],
        close=close,
    )

    request_candidate = observed_requests[0][0]
    assert request_candidate.candidate_id == composed_id
    assert request_candidate.strategy.params == {"threshold": 0.01}
    assert request_candidate.indicators[0].params == {"window": 20}


def test_validate_strategy_sweep_plan_requires_signal_materializer() -> None:
    with pytest.raises(TypeError, match="materialize_signals"):
        validate_strategy_sweep_plan(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_AXIS_KIND,
                "candidate_axis": [{"candidate_id": "fast", "params": {}}],
            },
            source_id="ma_cross",
        )


def test_strategy_sweep_materializer_cannot_emit_unrequested_candidates() -> None:
    close = _close_frame()

    def materialize(_request: SignalMaterializationRequest):
        return {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_SIGNALS_KIND,
            "entries": _surface(close, ["fast", "slow"], value=True),
            "exits": _surface(close, ["fast", "slow"], value=False),
        }

    plan = validate_strategy_sweep_plan(
        {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": STRATEGY_AXIS_KIND,
            "candidate_axis": [
                {"candidate_id": "fast", "params": {}},
                {"candidate_id": "slow", "params": {}},
            ],
            STRATEGY_MATERIALIZER_KEY: materialize,
        },
        source_id="ma_cross",
    )

    with pytest.raises(CandidateSweepError, match="candidate axis mismatch"):
        materialize_strategy_sweep_signals(
            plan,
            source_id="ma_cross",
            requested_candidate_ids=["fast"],
            close=close,
        )


def test_rejects_legacy_variant_records_in_sweep_contract() -> None:
    with pytest.raises(CandidateSweepError, match="legacy variant_records"):
        validate_strategy_sweep_axis({"variant_records": []}, source_id="ma_cross")


def test_rejects_duplicate_candidate_ids() -> None:
    with pytest.raises(CandidateSweepError, match="duplicate candidate"):
        validate_strategy_sweep_axis(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_AXIS_KIND,
                "candidate_axis": [
                    {"candidate_id": "fast", "params": {}},
                    {"candidate_id": "fast", "params": {}},
                ],
            },
            source_id="ma_cross",
        )


def test_rejects_candidate_ids_missing_param_tokens() -> None:
    params = {"entry_threshold": 40.0, "exit_threshold": 55.0}
    assert (
        candidate_id_from_params(
            "mean-revert",
            params,
            keys=("entry_threshold", "exit_threshold"),
        )
        == "mean-revert-40-55"
    )

    with pytest.raises(CandidateSweepError, match="parameter token"):
        validate_strategy_sweep_axis(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_AXIS_KIND,
                "candidate_axis": [
                    {
                        "candidate_id": "mean-revert-45-55",
                        "params": params,
                    }
                ],
            },
            source_id="rsi_reversion",
        )

    with pytest.raises(CandidateSweepError, match="parameter token"):
        validate_strategy_sweep_axis(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_AXIS_KIND,
                "candidate_axis": [
                    {"candidate_id": "threshold-0.01", "params": {"threshold": 0.0}}
                ],
            },
            source_id="ma_cross",
        )


def test_rejects_playbook_owned_metric_or_portfolio_fields() -> None:
    close = _close_frame()

    with pytest.raises(CandidateSweepError, match="metric or portfolio fields"):
        validate_strategy_sweep_signals(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_SIGNALS_KIND,
                "entries": _surface(close, ["fast"]),
                "exits": _surface(close, ["fast"]),
                "portfolio": {"entry_budget": 1.0},
            },
            source_id="ma_cross",
            expected_candidate_ids=["fast"],
            close=close,
        )


def test_rejects_signal_materialization_that_omits_requested_candidates() -> None:
    close = _close_frame()

    with pytest.raises(CandidateSweepError, match="candidate axis mismatch"):
        validate_strategy_sweep_signals(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_SIGNALS_KIND,
                "entries": _surface(close, ["fast"]),
                "exits": _surface(close, ["fast"]),
            },
            source_id="ma_cross",
            expected_candidate_ids=["fast", "slow"],
            close=close,
        )


def test_rejects_extra_strategy_signal_column_levels() -> None:
    close = _close_frame()
    columns = pd.MultiIndex.from_product(
        [["fast"], list(close.columns), ["extra"]],
        names=[CANDIDATE_LEVEL, SYMBOL_LEVEL, "debug_level"],
    )
    surface = pd.DataFrame(True, index=close.index, columns=columns)

    with pytest.raises(CandidateSweepError, match="exactly two levels"):
        validate_strategy_sweep_signals(
            {
                "contract": PLAYBOOK_SWEEP_CONTRACT,
                "kind": STRATEGY_SIGNALS_KIND,
                "entries": surface,
                "exits": surface,
            },
            source_id="ma_cross",
            expected_candidate_ids=["fast"],
            close=close,
        )


def test_composed_candidate_ids_preserve_source_boundaries_and_reject_duplicates() -> None:
    strategy_axis = CandidateAxis(
        source="playbook",
        source_id="ma_cross",
        candidates=(SweepCandidate(candidate_id="fast", params={}),),
    )
    indicator_axis = CandidateAxis(
        source="playbook",
        source_id="ma_explore",
        candidates=(SweepCandidate(candidate_id="ma-20", params={"window": 20}),),
    )

    assert composed_candidate_ids(
        strategy_axis=strategy_axis,
        indicator_axes=[indicator_axis],
    ) == ("strategy:playbook:ma_cross:fast+indicators:[playbook:ma_explore:ma-20]",)
    composed_candidate = compose_candidate_grid(
        strategy_axis=strategy_axis,
        indicator_axes=[indicator_axis],
    )[0]
    assert composed_candidate.strategy.params == {}
    assert composed_candidate.indicators[0].params == {"window": 20}

    duplicate_strategy_axis = CandidateAxis(
        source="playbook",
        source_id="ma_cross",
        candidates=(
            SweepCandidate(candidate_id="fast", params={}),
            SweepCandidate(candidate_id="fast", params={}),
        ),
    )
    with pytest.raises(CandidateSweepError, match="duplicate composed candidate ids"):
        composed_candidate_ids(strategy_axis=duplicate_strategy_axis)


def test_preflight_indicator_grid_reports_counts_and_limits() -> None:
    close = _close_frame()
    result = validate_indicator_sweep_result(
        {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": INDICATOR_RESULT_KIND,
            "candidate_axis": [
                {"candidate_id": "ma-2", "params": {}},
                {"candidate_id": "ma-5", "params": {}},
            ],
            "outputs": {"ma": _surface(close, ["ma-2", "ma-5"])},
        },
        source_id="ma_explore",
        close=close,
    )

    preflight = preflight_indicator_grid(
        [result],
        max_candidates=10,
        max_estimated_cells=20,
    )

    assert preflight.indicator_context_count == 2
    assert preflight.estimated_cells == 12
    assert preflight.diagnostics()["axes"] == [
        {
            "source": "playbook",
            "id": "ma_explore",
            "candidate_count": 2,
            "output_count": 1,
            "row_count": 3,
            "symbol_count": 2,
            "estimated_cells": 12,
        }
    ]


def test_preflight_indicator_grid_rejects_oversize_estimates() -> None:
    close = _close_frame()
    result = validate_indicator_sweep_result(
        {
            "contract": PLAYBOOK_SWEEP_CONTRACT,
            "kind": INDICATOR_RESULT_KIND,
            "candidate_axis": [
                {"candidate_id": "ma-2", "params": {}},
                {"candidate_id": "ma-5", "params": {}},
            ],
            "outputs": {"ma": _surface(close, ["ma-2", "ma-5"])},
        },
        source_id="ma_explore",
        close=close,
    )

    with pytest.raises(CandidateSweepError, match=r"candidate_grid\.max_estimated_cells") as error:
        preflight_indicator_grid([result], max_candidates=10, max_estimated_cells=11)

    assert error.value.diagnostics["estimated_cells"] == 12


def _close_frame() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=3, freq="D")
    return pd.DataFrame(
        {
            "AAPL": [100.0, 101.0, 102.0],
            "MSFT": [200.0, 201.0, 202.0],
        },
        index=index,
    )


def _surface(close: pd.DataFrame, candidate_ids: list[str], *, value: object = 1.0) -> pd.DataFrame:
    columns = pd.MultiIndex.from_product(
        [candidate_ids, list(close.columns)],
        names=[CANDIDATE_LEVEL, SYMBOL_LEVEL],
    )
    return pd.DataFrame(value, index=close.index, columns=columns)

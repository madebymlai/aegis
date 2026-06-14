from __future__ import annotations

from pathlib import Path

from research.aegis_research.optimization.candidate_evidence import candidate_rows_from_result
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.param_namespace import (
    FIXED_CANDIDATE_PARAM,
    ComponentRef,
    decode,
    encode,
    slice_by_component,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)


def test_component_param_keys_round_trip_to_component_slices() -> None:
    ref = ComponentRef("indicators", "demo.trend", "demo.trend")
    key = encode(ref, "window")

    assert decode(key) == (ref, "window")
    assert slice_by_component({key: 5, FIXED_CANDIDATE_PARAM: 0}) == {
        ref: {"window": 5}
    }


def test_golden_param_namespace_keys_pin_exact_hex_literals() -> None:
    """Pin the param-namespace wire format with literal-string assertions.

    A symmetric prefix/hex change would pass a round-trip test while silently
    re-keying every Candidate and orphaning every persisted Lock. These literal
    assertions are the regression oracle — they are the only tests that break on
    a format change.
    """
    indicator_key = encode(ComponentRef("indicators", "demo.mom", "demo.mom"), "window")
    assert (
        indicator_key
        == "component__696e64696361746f7273__64656d6f2e6d6f6d__64656d6f2e6d6f6d__77696e646f77"
    )

    strategy_key = encode(
        ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross"), "fast_window"
    )
    assert (
        strategy_key
        == "component__73747261746567696573__64656d6f2e6d615f63726f7373__73747261746567793a64656d6f2e6d615f63726f7373__666173745f77696e646f77"
    )


def test_stored_row_decode_through_candidate_store_path(tmp_path: Path) -> None:
    """Decode a stored Candidate row — not hand-synthesized — through the same
    insert/load path the lock resolver uses, then verify slice_by_component."""
    strategy_ref = ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross")
    indicator_ref = ComponentRef("indicators", "demo.mom", "demo.mom")
    fast_key = encode(strategy_ref, "fast_window")
    slow_key = encode(strategy_ref, "slow_window")
    window_key = encode(indicator_ref, "window")

    result = OptimizationResult(
        best=EvaluatedCandidate(
            params={fast_key: 2, slow_key: 10, window_key: 20},
            score=0.30,
            selection_metrics={0: {"total_return": 0.30}},
            metrics={"total_return": 0.30},
            held_out_metrics={0: {"total_return": 0.25}},
        ),
        median=EvaluatedCandidate(
            params={fast_key: 3, slow_key: 12, window_key: 22},
            score=0.20,
            selection_metrics={0: {"total_return": 0.20}},
            metrics={"total_return": 0.20},
            held_out_metrics={0: {"total_return": 0.15}},
        ),
        worst=EvaluatedCandidate(
            params={fast_key: 5, slow_key: 15, window_key: 25},
            score=0.10,
            selection_metrics={0: {"total_return": 0.10}},
            metrics={"total_return": 0.10},
            held_out_metrics={0: {"total_return": 0.05}},
        ),
    )
    rows = candidate_rows_from_result(
        result,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
        allocation_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="stored-decode-run",
            candidate_rows=rows,
            provenance={
                "run_id": "stored-decode-run",
                "source": {
                    "schema_version": "component_optimization_source.v2",
                    "source": "component",
                    "strategy": {
                        "family": "strategies",
                        "slot": "strategy:demo.ma_cross",
                        "id": "demo.ma_cross",
                        "version": "1.0.0",
                        "fixed_params": {},
                        "param_keys": {
                            "fast_window": fast_key,
                            "slow_window": slow_key,
                        },
                    },
                    "indicators": [
                        {
                            "family": "indicators",
                            "slot": "demo.mom",
                            "id": "demo.mom",
                            "version": "1.0.0",
                            "fixed_params": {},
                            "param_keys": {"window": window_key},
                        }
                    ],
                },
            },
        )

        median_key = store.candidate_key_for_role("stored-decode-run", "median")
        row = store.candidate_by_key(median_key, run_id="stored-decode-run")["candidate"]
    slices = slice_by_component(row["params"])

    assert strategy_ref in slices
    assert slices[strategy_ref] == {"fast_window": 3, "slow_window": 12}

    assert indicator_ref in slices
    assert slices[indicator_ref] == {"window": 22}

    assert FIXED_CANDIDATE_PARAM not in slices[strategy_ref]
    assert FIXED_CANDIDATE_PARAM not in slices[indicator_ref]
    for ref_key in slices:
        assert not isinstance(ref_key, str)

"""Unit tests for pipeline publishing stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.optimization.pipeline_publishing import run_pipeline_publishing
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_pipeline_publishing_returns_expected_keys(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """run_pipeline_publishing returns candidate_rows, leaderboard, lock_records,
    candidate_store_provenance, and optimization_evidence."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config

    class _FakeSource:
        evidence = {"strategy": {"family": "strategies", "id": "demo.strategy"}}

    class _FakeRun:
        evaluated_index = __import__("pandas").MultiIndex.from_tuples(
            [(0, "selection", "SYN", 0)], names=["split", "set", "symbol", "param_idx"]
        )
        selection = __import__("pandas").Index([0])
        sampled_rows_source = "grid-combinations"
        ranking_metric = "total_return"
        ranking_direction = "desc"

    class _FakeSplit:
        held_out_index = __import__("pandas").Index([1])

    class _FakeSplitResult:
        splits = [_FakeSplit(), _FakeSplit()]
        metadata = {"n_splits": 2}

    class _FakeRecorder:
        class manifest:
            run_id = "test-run-id"
            evidence: dict[str, Any] = {}

        def persist(self) -> None:
            pass

    class _FakeDataResult:
        class quality:
            state = "ok"

        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "loaded_arrays": ["Close", "Open"],
            "effective_arrays": ["OHLCV"],
            "shape": {"rows": 120},
        }

    class _FakeArrayContract:
        def metadata(self) -> dict[str, Any]:
            return {"required": ["Close", "Open"]}

    store_path = tmp_path / ".candidate_store" / "candidates.sqlite3"
    store_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "research.aegis_research.optimization.pipeline_publishing.publish_candidates",
        lambda **kwargs: None,
    )

    result = run_pipeline_publishing(
        config=config,
        recorder=_FakeRecorder(),
        data_result=_FakeDataResult(),
        array_contract=_FakeArrayContract(),
        optimization_source=_FakeSource(),
        optimization_run=_FakeRun(),
        run_payload={"sampled_rows": {"rows": [{"a": 1}]}},
        split_result=_FakeSplitResult(),
        portfolio_builtin={"target_exposure_cap": 1.0},
        optimization_evidence={"schema_version": "optimization_route.v1"},
        store_path=store_path,
        metric_registry_fingerprint=None,
    )

    expected_keys = {
        "candidate_rows",
        "leaderboard",
        "lock_records",
        "candidate_store_provenance",
        "optimization_evidence",
    }
    assert set(result.keys()) == expected_keys


def test_pipeline_publishing_updates_optimization_evidence_counts(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """optimization_evidence is updated with candidate_count and locks."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config

    class _FakeSource:
        evidence = {
            "strategy": {
                "family": "strategies",
                "id": "demo.strategy",
                "slot": "strategy",
                "params": {},
            },
            "indicators": [],
        }

    class _FakeRun:
        evaluated_index = __import__("pandas").MultiIndex.from_tuples(
            [(0, "selection", "SYN", 0)], names=["split", "set", "symbol", "param_idx"]
        )
        selection = __import__("pandas").Index([0])
        sampled_rows_source = "grid-combinations"
        ranking_metric = "total_return"
        ranking_direction = "desc"

    class _FakeSplit:
        held_out_index = __import__("pandas").Index([1])

    class _FakeSplitResult:
        splits = [_FakeSplit(), _FakeSplit()]
        metadata = {"n_splits": 2}

    class _FakeRecorder:
        class manifest:
            run_id = "test-run-id"
            evidence: dict[str, Any] = {}

        def persist(self) -> None:
            pass

    class _FakeDataResult:
        class quality:
            state = "ok"

        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "loaded_arrays": ["Close", "Open"],
            "effective_arrays": ["OHLCV"],
            "shape": {"rows": 120},
        }

    class _FakeArrayContract:
        def metadata(self) -> dict[str, Any]:
            return {"required": ["Close", "Open"]}

    store_path = tmp_path / ".candidate_store" / "candidates.sqlite3"
    store_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "research.aegis_research.optimization.pipeline_publishing.publish_candidates",
        lambda **kwargs: None,
    )

    result = run_pipeline_publishing(
        config=config,
        recorder=_FakeRecorder(),
        data_result=_FakeDataResult(),
        array_contract=_FakeArrayContract(),
        optimization_source=_FakeSource(),
        optimization_run=_FakeRun(),
        run_payload={"sampled_rows": {"rows": [{"a": 1}]}},
        split_result=_FakeSplitResult(),
        portfolio_builtin={"target_exposure_cap": 1.0},
        optimization_evidence={"schema_version": "optimization_route.v1"},
        store_path=store_path,
        metric_registry_fingerprint=None,
    )

    evidence = result["optimization_evidence"]
    assert evidence["candidate_count"] >= 0
    assert evidence["sampled_row_count"] == 1
    assert "locks" in evidence

"""Unit tests for pipeline execution stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.metrics.registry import empty_metric_registry
from research.aegis_research.optimization.evidence_ledger import RunEvidence
from research.aegis_research.optimization.pipeline.execution import run_pipeline_execution
from research.aegis_research.optimization.source import OptimizationSourceError
from tests.support.research.aegis_research.factories import make_setup_result
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_pipeline_execution_persists_and_raises_on_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PreflightError triggers persist and raises OptimizationSourceError."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config

    setup = make_setup_result(store_path=tmp_path / "store.sqlite3")

    persisted = []
    manifest_evidence: dict[str, Any] = {}
    run_evidence = RunEvidence(
        manifest_evidence,
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={"schema_version": "optimization_route.v1"},
        persist=lambda: persisted.append(True),
    )

    from research.aegis_research.optimization.preflight import PreflightError

    def _fail_preflight(**kwargs: Any) -> Any:
        raise PreflightError("preflight failed", diagnostics={"error": True})

    monkeypatch.setattr(
        "research.aegis_research.optimization.pipeline.execution.build_preflight",
        _fail_preflight,
    )

    with pytest.raises(OptimizationSourceError, match="preflight failed"):
        run_pipeline_execution(
            config=config,
            setup=setup,
            metric_registry=empty_metric_registry().freeze(),
            run_evidence=run_evidence,
        )

    assert len(persisted) == 1
    assert manifest_evidence["optimization"]["preflight"] == {"error": True}
    assert manifest_evidence["optimization"]["preflight_failure"] == {
        "error_type": "PreflightError",
        "message": "preflight failed",
    }

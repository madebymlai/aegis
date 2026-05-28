"""Unit tests for pipeline execution stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.optimization.pipeline.execution import run_pipeline_execution
from research.aegis_research.optimization.source import OptimizationSourceError
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

    class _FakeSource:
        params = {}
        evidence = {"strategy": {}}

    class _FakeSplitResult:
        metadata = {"n_splits": 2}
        splits = []

    persisted = []

    class _FakeRecorder:
        class manifest:
            evidence: dict[str, Any] = {}

        def persist(self) -> None:
            persisted.append(True)

    import pandas as pd

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
            optimization_source=_FakeSource(),
            close=pd.DataFrame({0: [1.0, 2.0]}),
            open_prices=pd.DataFrame({0: [1.0, 2.0]}),
            split_result=_FakeSplitResult(),
            optimization_evidence={"schema_version": "optimization_route.v1"},
            recorder=_FakeRecorder(),
        )

    assert len(persisted) == 1

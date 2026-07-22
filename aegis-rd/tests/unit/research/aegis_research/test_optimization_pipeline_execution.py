"""Unit tests for pipeline execution stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from vectorbtpro import vbt

from research.aegis_research.metrics.registry import empty_metric_registry
from research.aegis_research.optimization.evidence_ledger import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.execution import run_pipeline_execution
from research.aegis_research.optimization.portfolio_simulation import ResolvedBook
from research.aegis_research.optimization.source import OptimizationSource, OptimizationSourceError
from research.aegis_research.run_record.manifest import RunStage
from tests.support.research.aegis_research.factories import make_setup_result
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_pipeline_execution_persists_and_raises_on_preflight_failure(
    tmp_path: Path,
) -> None:
    """Insufficient post-warmup history persists evidence and fails before execution."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    source = OptimizationSource(
        precompute=lambda *args, **kwargs: pytest.fail("precompute must not run"),
        simulate=lambda *args, **kwargs: pytest.fail("Portfolio must not run"),
        resolve_lookbacks=lambda params: {"component": 0},
        params={"window": vbt.Param([1])},
        evidence={"strategy": {}},
    )
    setup = make_setup_result(
        store_path=tmp_path / "store.sqlite3",
        optimization_source=source,
    )

    persisted = []
    manifest_evidence: dict[str, Any] = {}
    run_evidence = RunEvidence(
        manifest_evidence,
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={"schema_version": OPTIMIZATION_ROUTE_SCHEMA_VERSION},
        persist=lambda: persisted.append(True),
    )

    with pytest.raises(OptimizationSourceError, match="at least two"):
        run_pipeline_execution(
            config=config,
            setup=setup,
            book=ResolvedBook.resolve(config.portfolio, setup.run_data),
            metric_registry=empty_metric_registry().freeze(),
            run_evidence=run_evidence,
        )

    assert len(persisted) == 1
    preflight = manifest_evidence["optimization"]["preflight"]
    assert preflight["loaded_rows"] == 2
    assert preflight["scored_rows"] == 2
    assert preflight["observation_block_bars"] == 20
    assert run_evidence.active_stage is RunStage.PREFLIGHT
    assert "preflight_failure" not in manifest_evidence["optimization"]

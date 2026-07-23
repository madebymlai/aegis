"""Unit tests for pipeline execution stage."""

from __future__ import annotations

from pathlib import Path

import pytest
from vectorbtpro import vbt

from research.aegis_research.metrics.registry import empty_metric_registry
from research.aegis_research.optimization.source import OptimizationSource, OptimizationSourceError
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run._stages.execution import run_pipeline_execution
from tests.support.research.aegis_research.factories import make_setup_result
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_pipeline_execution_raises_on_preflight_failure(
    tmp_path: Path,
) -> None:
    """Insufficient post-warmup history fails before execution."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    source = OptimizationSource(
        precompute=lambda *args, **kwargs: pytest.fail("precompute must not run"),
        simulate=lambda *args, **kwargs: pytest.fail("Portfolio must not run"),
        resolve_lookbacks=lambda params: {"component": 0},
        params={"window": vbt.Param([1])},
        identity={"strategy": {}},
    )
    setup = make_setup_result(
        store_path=tmp_path / "store.sqlite3",
        optimization_source=source,
    )

    with pytest.raises(OptimizationSourceError, match="at least two"):
        run_pipeline_execution(
            config=config,
            setup=setup,
            book=ResolvedBook.resolve(config.portfolio, setup.run_data),
            metric_registry=empty_metric_registry().freeze(),
        )

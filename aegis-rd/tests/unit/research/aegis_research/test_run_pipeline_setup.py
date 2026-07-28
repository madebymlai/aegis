"""Unit tests for pipeline setup stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.candidates.identity import candidate_store_path
from research.aegis_research.run._stages.setup import (
    SetupResult,
    run_pipeline_setup,
)
from tests.support.research.aegis_research.factories import (
    make_run_data,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def _run_data() -> Any:
    import pandas as pd

    frame = pd.DataFrame({0: [float(i) for i in range(120)]})
    return make_run_data(close=frame, open_=frame)


def test_pipeline_setup_returns_setup_result(
    tmp_path: Path,
) -> None:
    """run_pipeline_setup returns a typed SetupResult."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
    )

    assert isinstance(result, SetupResult)
    # Typed fields — constructor is the contract.
    assert result.store_path == candidate_store_path(config)
    assert result.optimization_source is not None
    assert result.run_data is not None
    assert not hasattr(result, "split_result")


def test_pipeline_setup_store_path_matches_candidate_store(
    tmp_path: Path,
) -> None:
    """store_path matches the expected candidate store path for the config."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
    )

    assert result.store_path == candidate_store_path(config)

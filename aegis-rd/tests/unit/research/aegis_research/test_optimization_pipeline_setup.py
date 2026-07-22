"""Unit tests for pipeline setup stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.optimization.candidate_store_identity import candidate_store_path
from research.aegis_research.optimization.evidence_ledger import RunEvidence
from research.aegis_research.optimization.pipeline.setup import (
    SetupResult,
    run_pipeline_setup,
)
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
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


def _run_evidence() -> RunEvidence:
    return RunEvidence(
        {},
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={},
        persist=lambda: None,
    )


def test_pipeline_setup_returns_setup_result(
    tmp_path: Path,
) -> None:
    """run_pipeline_setup returns a typed SetupResult."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
        array_contract=array_contract,
        metric_registry_fingerprint="metric-fp",
        run_evidence=_run_evidence(),
    )

    assert isinstance(result, SetupResult)
    # Typed fields — constructor is the contract.
    assert result.store_path == candidate_store_path(config)
    assert result.optimization_source is not None
    assert isinstance(result.strategy_evidence, dict)
    assert result.run_data is not None
    assert not hasattr(result, "split_result")


def test_pipeline_setup_evidence_baseline_shape(
    tmp_path: Path,
) -> None:
    """run evidence includes schema, contract, source, and param_names."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    run_evidence = _run_evidence()
    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
        array_contract=array_contract,
        metric_registry_fingerprint="metric-fp",
        run_evidence=run_evidence,
    )

    evidence = run_evidence.optimization()
    assert evidence["schema_version"] == "optimization_route.v2"
    assert "contract" in evidence
    assert "source" in evidence
    assert "param_names" in evidence
    assert evidence["open_prices_available"] is True
    assert "resolved_locks" not in evidence
    # strategy_evidence is derived from optimization_source — same object.
    assert result.strategy_evidence is result.optimization_source.evidence["strategy"]


def test_pipeline_setup_store_path_matches_candidate_store(
    tmp_path: Path,
) -> None:
    """store_path matches the expected candidate store path for the config."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
        array_contract=array_contract,
        metric_registry_fingerprint="metric-fp",
        run_evidence=_run_evidence(),
    )

    assert result.store_path == candidate_store_path(config)

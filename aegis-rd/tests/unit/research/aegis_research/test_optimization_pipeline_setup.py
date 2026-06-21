"""Unit tests for pipeline setup stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.evidence_ledger import RunEvidence
from research.aegis_research.optimization.pipeline.setup import (
    SetupResult,
    run_pipeline_setup,
)
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)
from tests.support.research.aegis_research.test_doubles import (
    FakeDataResult,
    default_metadata,
)

_OHLCV_METADATA = default_metadata(
    effective_arrays=["OHLCV"], start=None, end=None
)


class _FakeData:
    def array(self, name: str) -> Any:
        import pandas as pd

        return pd.DataFrame({0: [float(i) for i in range(120)]})


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
        data=_FakeData(),
        data_result=FakeDataResult(quality_state="ok", metadata=_OHLCV_METADATA),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=_run_evidence(),
    )

    assert isinstance(result, SetupResult)
    # Typed fields — constructor is the contract.
    assert result.store_path == candidate_store_path(config)
    assert result.optimization_source is not None
    assert isinstance(result.strategy_evidence, dict)
    assert result.close is not None
    assert result.open_ is not None
    assert result.split_result is not None


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
        data=_FakeData(),
        data_result=FakeDataResult(quality_state="ok", metadata=_OHLCV_METADATA),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=run_evidence,
    )

    evidence = run_evidence.optimization()
    assert evidence["schema_version"] == "optimization_route.v1"
    assert "contract" in evidence
    assert "source" in evidence
    assert "param_names" in evidence
    assert evidence["open_prices_available"] is True
    assert "resolved_locks" not in evidence
    # strategy_evidence is derived from optimization_source — same object.
    assert result.strategy_evidence is result.optimization_source.evidence["strategy"]


class _PnlFakeData:
    def array(self, name: str) -> Any:
        import pandas as pd

        return pd.DataFrame({0: [float(i) + 1000.0 for i in range(120)]})


def test_pipeline_setup_routes_pnl_series_to_pnl_prices(tmp_path: Path) -> None:
    """A supplied P&L series drives pnl_close/pnl_open; the signal series still drives close/open_."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=FakeDataResult(quality_state="ok", metadata=_OHLCV_METADATA),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=_run_evidence(),
        pnl_data=_PnlFakeData(),
    )

    assert result.close.iloc[0, 0] == 0.0  # signal series (indicators)
    assert result.pnl_close.iloc[0, 0] == 1000.0  # P&L series (portfolio)
    assert result.pnl_open.iloc[0, 0] == 1000.0


def test_pipeline_setup_pnl_prices_default_to_signal_without_pnl_data(tmp_path: Path) -> None:
    """No P&L series → the portfolio simulates on the signal series (single-series default)."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=FakeDataResult(quality_state="ok", metadata=_OHLCV_METADATA),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=_run_evidence(),
    )

    assert result.pnl_close is result.close
    assert result.pnl_open is result.open_


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
        data=_FakeData(),
        data_result=FakeDataResult(quality_state="ok", metadata=_OHLCV_METADATA),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=_run_evidence(),
    )

    assert result.store_path == candidate_store_path(config)

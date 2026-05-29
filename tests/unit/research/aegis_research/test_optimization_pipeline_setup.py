"""Unit tests for pipeline setup stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.pipeline.setup import run_pipeline_setup
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_pipeline_setup_returns_expected_keys(
    tmp_path: Path,
) -> None:
    """run_pipeline_setup returns all expected output keys."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    class _FakeData:
        def feature(self, name: str) -> Any:
            import pandas as pd

            return pd.DataFrame({0: [float(i) for i in range(120)]})

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

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
    )

    expected_keys = {
        "store_path",
        "resolved_component_params",
        "resolved_locks",
        "optimization_source",
        "strategy_evidence",
        "close",
        "open_",
        "split_result",
        "optimization_builtin",
        "portfolio_builtin",
        "optimization_evidence",
    }
    assert set(result.keys()) == expected_keys


def test_pipeline_setup_evidence_baseline_shape(
    tmp_path: Path,
) -> None:
    """optimization_evidence includes schema, contract, source, and param_names."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    class _FakeData:
        def feature(self, name: str) -> Any:
            import pandas as pd

            return pd.DataFrame({0: [float(i) for i in range(120)]})

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

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
    )

    evidence = result["optimization_evidence"]
    assert evidence["schema_version"] == "optimization_route.v1"
    assert "contract" in evidence
    assert "source" in evidence
    assert "param_names" in evidence
    assert evidence["open_prices_available"] is True
    assert "resolved_locks" in evidence


def test_pipeline_setup_store_path_matches_candidate_store(
    tmp_path: Path,
) -> None:
    """store_path matches the expected candidate store path for the config."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    class _FakeData:
        def feature(self, name: str) -> Any:
            import pandas as pd

            return pd.DataFrame({0: [float(i) for i in range(120)]})

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

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
    )

    assert result["store_path"] == candidate_store_path(config)

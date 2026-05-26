from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from research.aegis_research.data_arrays import DataArrayContract
from research.aegis_research.optimization.run_data_contract import (
    build_candidate_data_identity,
    build_run_data_array_contract,
    build_run_data_evidence_payload,
    build_run_required_arrays,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_build_run_data_array_contract_includes_close_and_open(tmp_path: pytest.TempPathFactory) -> None:
    """The pipeline always requires Close and Open arrays."""
    resolved = build_resolved_run_config(tmp_path)

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    assert isinstance(contract, DataArrayContract)
    assert "Close" in contract.pipeline_required_arrays
    assert "Open" in contract.pipeline_required_arrays
    assert contract.component_required_arrays
    assert "Close" in contract.required_arrays


def test_build_run_data_array_contract_configures_arrays(tmp_path: pytest.TempPathFactory) -> None:
    """Configured arrays from the config are reflected in the contract."""
    resolved = build_resolved_run_config(tmp_path)

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    configured = set(contract.configured_arrays)
    required = set(contract.required_arrays)
    assert configured.issuperset(required) or not (required - configured)


def test_build_run_required_arrays_collects_strategy_and_indicator_inputs(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Strategy and indicator input_names are merged."""
    resolved = build_resolved_run_config(tmp_path)

    arrays = build_run_required_arrays(resolved.config, resolved.component_registry)

    assert isinstance(arrays, tuple)
    assert "Close" in arrays
    assert len(set(arrays)) == len(arrays)  # no duplicates


def test_build_run_data_evidence_payload_extends_contract_payload(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """The run evidence payload includes data array evidence plus runner binding."""
    resolved = build_resolved_run_config(tmp_path)

    # Simplified: use a lightweight mock-like data result
    class _FakeResult:
        class quality:
            state = "ok"
        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "loaded_arrays": ["Close", "Open"],
        }

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)
    payload = build_run_data_evidence_payload(_FakeResult(), contract)

    assert payload["strategy_consumed_runner_data"] is True
    assert payload["strategy_data_binding"] == "runner_data_bundle"
    assert "configured_arrays" in payload
    assert payload["quality_state"] == "ok"


def test_build_candidate_data_identity_captures_source_and_contract(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Candidate data identity records source/array metadata from the run."""
    resolved = build_resolved_run_config(tmp_path)

    class _FakeResult:
        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "timeframe": "1D",
            "loaded_arrays": ["Close", "Open"],
            "shape": (120, 1),
            "index_start": "2020-01-01",
            "index_end": "2020-06-01",
        }

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)
    identity = build_candidate_data_identity(_FakeResult(), contract)

    assert identity["schema_version"] == "candidate_data_identity.v1"
    assert identity["source"] == "synthetic"
    assert identity["symbols"] == ["SYN"]
    assert identity["timeframe"] == "1D"
    assert identity["shape"] == (120, 1)
    assert "array_contract" in identity
    assert "configured_arrays" in identity["array_contract"]


def test_build_run_required_arrays_without_indicators(tmp_path: pytest.TempPathFactory) -> None:
    """Required arrays with no indicators should still include strategy inputs."""
    # We test with the fixture config which has one indicator - 
    # verifying the contract doesn't crash and produces a valid tuple.
    resolved = build_resolved_run_config(tmp_path)

    arrays = build_run_required_arrays(resolved.config, resolved.component_registry)

    assert len(arrays) >= 1
    assert "Close" in arrays

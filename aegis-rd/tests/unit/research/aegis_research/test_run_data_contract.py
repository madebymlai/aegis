from __future__ import annotations

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType

from research.aegis_research.run.data_contract import (
    DataArrayContract,
    build_run_data_array_contract,
    build_run_required_arrays,
    candidate_data_identity,
    run_data_evidence_payload,
)
from tests.support.research.aegis_research.factories import make_run_data
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_build_run_data_array_contract_includes_close_and_open(
    tmp_path: pytest.TempPathFactory,
) -> None:
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
    assert configured.issuperset(required)


def test_build_run_required_arrays_collects_strategy_and_indicator_inputs(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Strategy and indicator input_names are merged."""
    resolved = build_resolved_run_config(tmp_path)

    arrays = build_run_required_arrays(resolved.config, resolved.component_registry)

    assert isinstance(arrays, tuple)
    assert "Close" in arrays
    assert len(set(arrays)) == len(arrays)  # no duplicates


def test_evidence_payload_extends_contract_payload(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """The run evidence payload includes data array evidence plus runner binding."""
    resolved = build_resolved_run_config(tmp_path)

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)
    payload = run_data_evidence_payload(make_run_data(), contract)

    assert payload["schema_version"] == "run_data.v1"
    assert payload["loaded_arrays"] == ["Close", "Open"]
    assert "quality_state" not in payload
    assert payload["array_contract"]["configured_arrays"]


def test_candidate_data_identity_captures_instrument_ids_and_contract(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Candidate data identity records instrument-id/array metadata from the run."""
    resolved = build_resolved_run_config(tmp_path)

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)
    identity = candidate_data_identity(make_run_data(), contract)

    assert identity["schema_version"] == "candidate_data_identity.v4"
    assert identity["requested_instrument_ids"] == ["SYN.XNAS"]
    assert identity["tradeables"] == [{"instrument_id": "SYN.XNAS"}]
    assert identity["timeframe"] == "1D"
    assert identity["loaded_arrays"] == ["Close", "Open"]
    assert identity["rows"] == 2
    assert identity["index_start"] == "0"
    assert identity["index_end"] == "1"
    assert "array_contract" in identity
    assert "configured_arrays" in identity["array_contract"]


def test_candidate_data_identity_records_the_materialised_adjustment_mode(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    identity = candidate_data_identity(
        make_run_data(adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO),
        contract,
    )

    assert identity["adjustment_mode"] == "backward_ratio"


def test_candidate_data_identity_omits_the_mode_key_without_futures(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    identity = candidate_data_identity(make_run_data(), contract)

    assert identity["adjustment_mode"] is None


def test_evidence_payload_records_the_materialised_adjustment_mode(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    payload = run_data_evidence_payload(
        make_run_data(adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD),
        contract,
    )

    assert payload["adjustment_mode"] == "backward_spread"


def test_evidence_payload_omits_the_mode_key_without_futures(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    payload = run_data_evidence_payload(make_run_data(), contract)

    assert payload["adjustment_mode"] is None

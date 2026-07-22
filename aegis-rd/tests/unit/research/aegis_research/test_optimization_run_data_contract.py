from __future__ import annotations

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.optimization.run_data_contract import (
    DataArrayContract,
    build_run_data_array_contract,
    build_run_required_arrays,
)
from tests.support.research.aegis_research.factories import make_run_data_facts
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)
from tests.support.research.aegis_research.test_doubles import (
    FakeDataResult,
    default_metadata,
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
    facts = make_run_data_facts(
        data_result=FakeDataResult(
            quality_state="ok", metadata=default_metadata(rows=0, start=None, end=None)
        ),
        array_contract=contract,
    )
    payload = facts.evidence_payload()

    assert payload["strategy_consumed_runner_data"] is True
    assert payload["strategy_data_binding"] == "runner_data_bundle"
    assert "configured_arrays" in payload
    assert payload["quality_state"] == "ok"


def test_candidate_data_identity_captures_instrument_ids_and_contract(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Candidate data identity records instrument-id/array metadata from the run."""
    resolved = build_resolved_run_config(tmp_path)

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)
    identity = make_run_data_facts(array_contract=contract).candidate_data_identity()

    assert identity["schema_version"] == "candidate_data_identity.v3"
    assert identity["requested_instrument_ids"] == [_id("SYN.XNAS")]
    assert identity["instrument_ids"] == [_id("SYN.XNAS")]
    assert to_builtin(identity)["requested_instrument_ids"] == ["SYN.XNAS"]
    assert identity["timeframe"] == "1D"
    assert identity["loaded_arrays"] == ["Close", "Open"]
    assert identity["rows"] == 120
    assert identity["index_start"] == "2020-01-01"
    assert identity["index_end"] == "2020-06-01"
    assert "array_contract" in identity
    assert "configured_arrays" in identity["array_contract"]


def test_candidate_data_identity_records_the_materialised_adjustment_mode(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    identity = make_run_data_facts(
        data_result=FakeDataResult(adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO),
        array_contract=contract,
    ).candidate_data_identity()

    assert identity["adjustment_mode"] == "backward_ratio"


def test_candidate_data_identity_omits_the_mode_key_without_futures(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    identity = make_run_data_facts(array_contract=contract).candidate_data_identity()

    assert "adjustment_mode" not in identity


def test_evidence_payload_records_the_materialised_adjustment_mode(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    payload = make_run_data_facts(
        data_result=FakeDataResult(adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD),
        array_contract=contract,
    ).evidence_payload()

    assert payload["adjustment_mode"] == "backward_spread"


def test_evidence_payload_omits_the_mode_key_without_futures(
    tmp_path: pytest.TempPathFactory,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    payload = make_run_data_facts(array_contract=contract).evidence_payload()

    assert "adjustment_mode" not in payload


def test_metadata_artifact_payload_merges_metadata_and_contract(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """The data metadata artifact payload is the serialised metadata plus contract facts."""
    resolved = build_resolved_run_config(tmp_path)
    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)

    payload = make_run_data_facts(array_contract=contract).metadata_artifact_payload()

    assert payload["schema_version"] == "market_data.v4"
    assert payload["request"]["timeframe"] == "1D"
    assert payload["configured_arrays"] == ["Open", "High", "Low", "Close", "Volume"]
    assert payload["contract_required_arrays"] == ["Close", "Open"]


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)

from __future__ import annotations

from typing import ClassVar

import pytest

from research.aegis_research.market_data.contracts import (
    ArrayDescriptor,
    CoverageFacet,
    MarketDataMetadataV3,
    ProvenanceFacet,
    RequestFacet,
)
from research.aegis_research.optimization.run_data_contract import (
    DataArrayContract,
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


def test_build_run_data_evidence_payload_extends_contract_payload(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """The run evidence payload includes data array evidence plus runner binding."""
    resolved = build_resolved_run_config(tmp_path)

    # Simplified: use a lightweight mock-like data result
    class _FakeResult:
        class quality:
            state = "ok"
        metadata = MarketDataMetadataV3(
            schema_version="market_data.v3",
            request=RequestFacet(
                source="synthetic",
                requested_symbols=["SYN"],
                timeframe="1D",
                authored_arrays=["Close", "Open"],
                effective_arrays=["Close", "Open"],
            ),
            arrays=[
                ArrayDescriptor(name="Close", required=True, loaded=True, observed=True, ohlc=True),
                ArrayDescriptor(name="Open", required=True, loaded=True, observed=True, ohlc=True),
            ],
            coverage=CoverageFacet(
                symbols=["SYN"], rows=0, start=None, end=None
            ),
            quality={"state": "ok"},
            diagnostics=[],
            provenance=ProvenanceFacet(
                provider_class=None,
                source_metadata={},
                index_evidence={},
                provider_metadata={},
                omitted_metadata_fields=[],
                update_supported=False,
                missing_index="raise",
                missing_columns="raise",
                tz_localize=None,
                tz_convert=None,
                skip_on_error=False,
                silence_warnings=False,
            ),
        )

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
        metadata = MarketDataMetadataV3(
            schema_version="market_data.v3",
            request=RequestFacet(
                source="synthetic",
                requested_symbols=["SYN"],
                timeframe="1D",
                authored_arrays=["Close", "Open"],
                effective_arrays=["Close", "Open"],
            ),
            arrays=[
                ArrayDescriptor(name="Close", required=True, loaded=True, observed=True, ohlc=True),
                ArrayDescriptor(name="Open", required=True, loaded=True, observed=True, ohlc=True),
            ],
            coverage=CoverageFacet(
                symbols=["SYN"], rows=120, start="2020-01-01", end="2020-06-01"
            ),
            quality={"state": "healthy"},
            diagnostics=[],
            provenance=ProvenanceFacet(
                provider_class=None,
                source_metadata={},
                index_evidence={},
                provider_metadata={},
                omitted_metadata_fields=[],
                update_supported=False,
                missing_index="raise",
                missing_columns="raise",
                tz_localize=None,
                tz_convert=None,
                skip_on_error=False,
                silence_warnings=False,
            ),
        )

    contract = build_run_data_array_contract(resolved.config, resolved.component_registry)
    identity = build_candidate_data_identity(_FakeResult(), contract)

    assert identity["schema_version"] == "candidate_data_identity.v2"
    assert identity["source"] == "synthetic"
    assert identity["symbols"] == ["SYN"]
    assert identity["timeframe"] == "1D"
    assert identity["loaded_arrays"] == ["Close", "Open"]
    assert identity["rows"] == 120
    assert identity["index_start"] == "2020-01-01"
    assert identity["index_end"] == "2020-06-01"
    assert "array_contract" in identity
    assert "configured_arrays" in identity["array_contract"]

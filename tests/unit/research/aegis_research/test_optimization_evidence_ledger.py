from __future__ import annotations

from typing import Any

import pytest

from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    EvidenceSection,
    RunEvidence,
)


def test_run_evidence_seeds_manifest_and_records_optimization_sections() -> None:
    manifest_evidence: dict[str, Any] = {}
    persisted: list[bool] = []
    ledger = RunEvidence(
        manifest_evidence,
        component_registry_fingerprint="registry-fp",
        data_arrays={"schema_version": "data_array_contract.v1", "arrays": ("Close", "Open")},
        optimization={"contract": "optimization_source.v1", "param_names": ["fast"]},
        persist=lambda: persisted.append(True),
    )

    ledger.record(EvidenceSection.PREFLIGHT, {"eligible_candidate_count": 3})
    ledger.record(
        EvidenceSection.CANDIDATES,
        [
            {"role": "best", "candidate_key": "cand_a"},
            {"role": "median", "candidate_key": "cand_b"},
            {"role": "worst", "candidate_key": "cand_a"},
        ],
    )

    assert persisted == []
    assert manifest_evidence == {
        "component_registry_fingerprint": "registry-fp",
        "data_arrays": {"schema_version": "data_array_contract.v1", "arrays": ["Close", "Open"]},
        "optimization": {
            "schema_version": "optimization_route.v1",
            "contract": "optimization_source.v1",
            "param_names": ["fast"],
            "preflight": {"eligible_candidate_count": 3},
            "candidates": [
                {"role": "best", "candidate_key": "cand_a"},
                {"role": "median", "candidate_key": "cand_b"},
                {"role": "worst", "candidate_key": "cand_a"},
            ],
            "candidate_count": 2,
        },
    }

    snapshot = ledger.snapshot()
    snapshot["optimization"]["preflight"] = {"mutated": True}
    assert manifest_evidence["optimization"]["preflight"] == {"eligible_candidate_count": 3}


def test_run_evidence_fail_records_typed_failure_and_persists() -> None:
    manifest_evidence: dict[str, Any] = {}
    persisted: list[bool] = []
    ledger = RunEvidence(
        manifest_evidence,
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={},
        persist=lambda: persisted.append(True),
    )

    ledger.fail(EvidenceFailureStage.PUBLISHING, RuntimeError("candidate store unavailable"))

    assert persisted == [True]
    assert manifest_evidence["optimization"]["publishing_failure"] == {
        "error_type": "RuntimeError",
        "message": "candidate store unavailable",
    }


def test_run_evidence_rejects_untyped_section_keys() -> None:
    ledger = RunEvidence(
        {},
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={},
        persist=lambda: None,
    )

    with pytest.raises(TypeError, match="EvidenceSection"):
        ledger.record("preflight", {})  # type: ignore[arg-type]

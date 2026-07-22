from __future__ import annotations

import json
from pathlib import Path

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.run_record.capture import (
    canonical_hash,
    capture_config_evidence,
)
from research.aegis_research.run_record.manifest import (
    RunManifest,
    RunStatus,
    validate_manifest,
)
from tests.support.research.aegis_research.run_config_fixtures import build_resolved_run_config


def test_manifest_record_serializes_minimal_inventory(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        config={"schema_version": 1},
    )

    payload = manifest.to_dict()

    assert payload["schema_version"] == 6
    assert payload["run"]["id"] == "run-1"
    assert str(tmp_path) not in json.dumps(payload)
    assert payload["run"]["status"] == RunStatus.RUNNING
    assert set(payload["run"]) == {"id", "status", "started_at", "finished_at"}
    assert "lineage" not in payload
    assert "stages" not in payload
    assert "artifacts" not in payload
    validate_manifest(payload)


def test_canonical_hash_is_deterministic_for_normal_payload() -> None:
    assert canonical_hash({"b": 2, "a": 1}) == (
        "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    )


def test_canonical_hash_serializes_non_finite_values_as_null() -> None:
    payload = {"value": float("nan")}

    assert canonical_json_bytes(payload) == b'{"value":null}'
    assert canonical_hash(payload) == (
        "1c197daef20de3f47eec5e2f735ec6669869d3180cc29f35be4788511e0af0f8"
    )


def test_config_evidence_preserves_the_published_shape_and_hashes(tmp_path: Path) -> None:
    config = build_resolved_run_config(tmp_path)

    evidence = capture_config_evidence(config)

    assert evidence == {
        "schema_version": 11,
        "source_path": None,
        "authored_config_hash": "7bcfeb2ce1cdebb4e6c43c829d1aa243720cf09555bc63047c8d98c0b88ccbb5",
        "resolved_config_hash": "3ab786ce48e9bc91c4cd52f1b55d13d9cd11640ad2e8a4263808b6f77c02040e",
        "raw_config_identity": {
            "hash": "e974d53bedd622f6c027fb410e0a2b0e8dff93dd513da1134aafbd25e30967e6"
        },
    }

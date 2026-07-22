"""Unit tests for the golden-bytes comparison support (aegis-rd-0vh).

The oracle's value is that it fails when substantive Manifest bytes move and
stays quiet when only volatile fields (timestamps, host environment) differ —
both directions are pinned here against the support helper's public surface.
"""

from __future__ import annotations

import pytest

from tests.support.research.aegis_research.golden import (
    UPDATE_GOLDENS_ENV,
    assert_matches_golden,
    masked_canonical_manifest,
)


def _manifest(**overrides: object) -> dict:
    base: dict = {
        "schema_version": 6,
        "run": {
            "id": "oracle",
            "status": "completed",
            "started_at": "2026-06-10T08:00:00Z",
            "finished_at": "2026-06-10T08:00:09Z",
        },
        "config": {"name": "golden_bytes_oracle"},
        "evidence": {
            "environment": {"python": "3.13.1", "platform": "Linux-x", "packages": {}},
            "optimization": {"total": 30},
        },
    }
    base.update(overrides)
    return base


def test_masked_bytes_identical_when_only_volatile_fields_differ() -> None:
    earlier = _manifest()
    later = _manifest(
        run={
            "id": "oracle",
            "status": "completed",
            "started_at": "2027-01-01T00:00:00Z",
            "finished_at": "2027-01-01T11:11:11Z",
        },
        evidence={
            "environment": {"python": "3.99.0", "platform": "Darwin-y", "packages": {"numpy": "9"}},
            "optimization": {"total": 30},
        },
    )

    assert masked_canonical_manifest(earlier) == masked_canonical_manifest(later)


def test_masked_bytes_differ_when_substantive_field_moves() -> None:
    baseline = _manifest()
    drifted = _manifest(evidence={"optimization": {"total": 31}})

    assert masked_canonical_manifest(baseline) != masked_canonical_manifest(drifted)


def test_mismatch_raises_with_diff_and_regeneration_hint(tmp_path) -> None:
    golden = tmp_path / "golden.json"
    golden.write_bytes(masked_canonical_manifest(_manifest()))
    drifted = masked_canonical_manifest(_manifest(config={"name": "other_run"}))

    with pytest.raises(AssertionError, match=UPDATE_GOLDENS_ENV) as excinfo:
        assert_matches_golden(drifted, golden)
    assert "other_run" in str(excinfo.value)


def test_missing_golden_raises_with_generation_instruction(tmp_path) -> None:
    with pytest.raises(AssertionError, match="golden file missing"):
        assert_matches_golden(b"{}", tmp_path / "absent.json")


def test_update_env_writes_golden_instead_of_comparing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(UPDATE_GOLDENS_ENV, "1")
    golden = tmp_path / "nested" / "golden.json"

    assert_matches_golden(b'{"fresh": true}', golden)

    assert golden.read_bytes() == b'{"fresh": true}'


def test_matching_bytes_pass_silently(tmp_path) -> None:
    golden = tmp_path / "golden.json"
    payload = masked_canonical_manifest(_manifest())
    golden.write_bytes(payload)

    assert_matches_golden(payload, golden)

"""Seam tests for the run-refs callback contract (ADR-0016 / aegis-rd-4rq.3).

The orchestrator fires ``on_run_refs`` twice on failure and interrupt paths:
once at Run creation with ``running`` status, and again after the recorder
persists the terminal status just before the exception propagates.
Success fires only the start event; the returned result carries the final refs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research.aegis_research import cli
from research.aegis_research.provenance.manifest import RunStatus
from research.aegis_research.run_pipeline import run_strategy_sweep
from tests.support.research.aegis_research.run_config_fixtures import build_resolved_run_config

# ---------------------------------------------------------------------------
# Two-firing contract on failure
# ---------------------------------------------------------------------------


def test_on_run_refs_fires_twice_on_run_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The callback fires with running refs at start, then with failed refs at terminal."""
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)
    firings: list[dict[str, Any]] = []

    def record_refs(refs: dict[str, Any]) -> None:
        firings.append(dict(refs))

    def fail_after_manifest(_config, **_kwargs):
        raise RuntimeError("data stage failed")

    monkeypatch.setattr(
        "research.aegis_research.run_pipeline.load_run_data",
        fail_after_manifest,
    )

    with pytest.raises(RuntimeError, match="data stage failed"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="firing-failed-run",
            on_run_refs=record_refs,
        )

    assert len(firings) == 2
    assert firings[0]["status"] == RunStatus.RUNNING
    assert firings[0]["finished_at"] is None
    assert firings[1]["status"] == RunStatus.FAILED
    assert firings[1]["finished_at"] is not None
    # The six-field shape is identical at both moments.
    for key in ("run_id", "run_dir", "manifest_path", "status", "started_at", "finished_at"):
        assert key in firings[0]
        assert key in firings[1]
    assert firings[0]["run_id"] == firings[1]["run_id"]


def test_on_run_refs_fires_twice_on_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The callback fires with running refs at start, then with interrupted refs at terminal."""
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)
    firings: list[dict[str, Any]] = []

    def record_refs(refs: dict[str, Any]) -> None:
        firings.append(dict(refs))

    def interrupt_after_manifest(_config, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "research.aegis_research.run_pipeline.load_run_data",
        interrupt_after_manifest,
    )

    with pytest.raises(KeyboardInterrupt):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="firing-interrupted-run",
            on_run_refs=record_refs,
        )

    assert len(firings) == 2
    assert firings[0]["status"] == RunStatus.RUNNING
    assert firings[0]["finished_at"] is None
    assert firings[1]["status"] == RunStatus.INTERRUPTED
    assert firings[1]["finished_at"] is not None
    manifest = json.loads(
        (tmp_path / "runs" / "firing-interrupted-run" / "manifest.json").read_text()
    )
    assert manifest["run"]["failure"] == {
        "stage": "data",
        "error_type": "KeyboardInterrupt",
        "message": "interrupted",
    }
    for key in ("run_id", "run_dir", "manifest_path", "status", "started_at", "finished_at"):
        assert key in firings[0]
        assert key in firings[1]
    assert firings[0]["run_id"] == firings[1]["run_id"]


# ---------------------------------------------------------------------------
# Terminal callback raise chains the original failure as context
# ---------------------------------------------------------------------------


def test_terminal_callback_raise_chains_original_failure_as_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the callback raises during the terminal firing, the callback error
    carries the Run's real failure as its __context__."""
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)
    firing_count = 0

    def fail_on_terminal_only(refs: dict[str, Any]) -> None:
        nonlocal firing_count
        firing_count += 1
        if firing_count > 1:
            raise RuntimeError("terminal callback failed")

    def fail_data_loading(_config, **_kwargs):
        raise RuntimeError("data stage failed")

    monkeypatch.setattr(
        "research.aegis_research.run_pipeline.load_run_data",
        fail_data_loading,
    )

    with pytest.raises(RuntimeError, match="terminal callback failed") as exc_info:
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="context-chain-run",
            on_run_refs=fail_on_terminal_only,
        )

    # The callback error propagates, with the original failure as __context__.
    assert exc_info.value.__context__ is not None
    assert "data stage failed" in str(exc_info.value.__context__)


# ---------------------------------------------------------------------------
# Pre-Run config error yields envelope with no run block
# ---------------------------------------------------------------------------


def test_config_error_before_run_creation_omits_run_block_in_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Run Config rejected before any Run is created produces an error JSON
    envelope with no ``run`` block — exactly as today."""
    monkeypatch.chdir(tmp_path)

    assert cli.main(["run", "missing.yaml"]) == 6

    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "error"
    assert payload["error"]["category"] == "config_validation"
    assert "run" not in payload


def test_manifest_marks_starting_callback_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the callback itself raises at start time, the run is still marked failed
    in the manifest (existing contract, parameter renamed)."""
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)

    def fail_callback(_refs):
        raise RuntimeError("start callback failed")

    with pytest.raises(RuntimeError, match="start callback failed"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="start-callback-failed-run",
            on_run_refs=fail_callback,
        )

    manifest = json.loads(
        (tmp_path / "runs" / "start-callback-failed-run" / "manifest.json").read_text()
    )
    assert manifest["run"]["status"] == RunStatus.FAILED

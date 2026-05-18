from __future__ import annotations

import nbformat
import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.playbook_registry import (
    PlaybookRegistryError,
    PlaybookSelection,
    discover_playbook_registry,
)
from research.aegis_research.playbook_registry.registry import execute_notebook_playbook


def test_playbook_registry_discovers_stable_ids_and_executes_selected_notebook(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    notebook = root / "indicators" / "ma_explore.ipynb"
    _write_notebook(notebook, "indicators", "ma_explore")

    registry = discover_playbook_registry(root=root, repo_root=tmp_path)
    definition = registry.get(PlaybookSelection("indicators", "ma_explore"))

    result = execute_notebook_playbook(definition, params={"window": 5})

    assert registry.ids("indicators") == ("ma_explore",)
    assert definition.identity.repo_relative_path == "research/playbooks/indicators/ma_explore.ipynb"
    assert result["variant_records"] == [{"id": "ma_explore", "window": 5}]


def test_playbook_registry_rejects_duplicate_ids(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_notebook(root / "indicators" / "one.ipynb", "indicators", "duplicate")
    _write_notebook(root / "indicators" / "two.ipynb", "indicators", "duplicate")

    with pytest.raises(PlaybookRegistryError, match="duplicate playbook id"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_playbook_registry_rejects_unsupported_stage(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_notebook(
        root / "indicators" / "bad_stage.ipynb",
        "indicators",
        "bad_stage",
        stages=["signals"],
    )

    with pytest.raises(PlaybookRegistryError, match="unsupported stage"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_indicator_playbook_rejects_multiple_indicator_families(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_notebook(
        root / "indicators" / "too_many.ipynb",
        "indicators",
        "too_many",
        indicator_families=["ma", "rsi"],
    )

    with pytest.raises(PlaybookRegistryError, match="one indicator family"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_indicator_playbook_rejects_unknown_baseline_component(tmp_path) -> None:
    playbook_root = tmp_path / "research" / "playbooks"
    component_root = tmp_path / "research" / "components"
    _write_notebook(
        playbook_root / "indicators" / "baseline.ipynb",
        "indicators",
        "baseline",
        baseline_component_indicator_id="missing.component",
    )
    component_registry = discover_component_registry(root=component_root, repo_root=tmp_path)

    with pytest.raises(PlaybookRegistryError, match="unknown baseline component indicator"):
        discover_playbook_registry(
            root=playbook_root,
            repo_root=tmp_path,
            component_registry=component_registry,
        )


def _write_notebook(
    path,
    family: str,
    playbook_id: str,
    *,
    stages: list[str] | None = None,
    indicator_families: list[str] | None = None,
    baseline_component_indicator_id: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": stages or [family],
        "accepted_inputs": ["close"],
        "result_schema": "playbook_result.v1",
    }
    if family == "indicators":
        metadata["indicator_family"] = "ma"
        if indicator_families is not None:
            metadata["indicator_families"] = indicator_families
        if baseline_component_indicator_id is not None:
            metadata["baseline_component_indicator_id"] = baseline_component_indicator_id
    nb = nbformat.v4.new_notebook(
        metadata={"aegis_playbook": metadata},
        cells=[
            nbformat.v4.new_code_cell(
                "AEGIS_PLAYBOOK_RESULT = {"
                "'variant_records': [{'id': '"
                + playbook_id
                + "', 'window': AEGIS_PLAYBOOK_PARAMS.get('window')}]}"
            )
        ],
    )
    nbformat.write(nb, path)

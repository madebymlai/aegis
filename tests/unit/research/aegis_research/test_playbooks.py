from __future__ import annotations

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.playbook_registry import (
    PLAYBOOK_FAMILIES,
    PlaybookRegistryError,
    PlaybookSelection,
    discover_playbook_registry,
)


def test_playbook_registry_discovers_stable_ids_and_loads_selected_playbook(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    playbook = root / "indicators" / "ma_explore.py"
    _write_playbook(playbook, "indicators", "ma_explore")

    registry = discover_playbook_registry(root=root, repo_root=tmp_path)
    definition = registry.get(PlaybookSelection("indicators", "ma_explore"))

    result = definition.load_callable()(None)

    assert registry.ids("indicators") == ("ma_explore",)
    assert definition.identity.repo_relative_path == "research/playbooks/indicators/ma_explore.py"
    assert result["contract"] == "aegis.playbook_sweep.v1"
    assert result["candidate_axis"] == [{"candidate_id": "ma_explore-5", "params": {"window": 5}}]


def test_active_playbook_families_are_run_only() -> None:
    assert PLAYBOOK_FAMILIES == ("indicators", "strategies")


def test_playbook_owns_static_params(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    playbook = root / "indicators" / "ma_explore.py"
    _write_playbook(playbook, "indicators", "ma_explore")
    registry = discover_playbook_registry(root=root, repo_root=tmp_path)
    definition = registry.get(PlaybookSelection("indicators", "ma_explore"))

    result = definition.load_callable()(None)

    assert result["contract"] == "aegis.playbook_sweep.v1"
    assert result["candidate_axis"] == [{"candidate_id": "ma_explore-5", "params": {"window": 5}}]


def test_playbook_registry_rejects_duplicate_ids(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(root / "indicators" / "one.py", "indicators", "duplicate")
    _write_playbook(root / "indicators" / "two.py", "indicators", "duplicate")

    with pytest.raises(PlaybookRegistryError, match="duplicate playbook id"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_indicator_playbook_rejects_literal_candidate_id_with_params(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_literal_candidate_id_playbook(root / "indicators" / "bad_indicator.py", "indicators")

    with pytest.raises(PlaybookRegistryError, match="candidate_id values with params"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_strategy_playbook_rejects_literal_candidate_id_with_params(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_literal_candidate_id_playbook(root / "strategies" / "bad_strategy.py", "strategies")

    with pytest.raises(PlaybookRegistryError, match="candidate_id values with params"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


@pytest.mark.parametrize("family", ["indicators", "strategies"])
def test_playbook_allows_literal_candidate_id_for_named_logic_without_params(
    tmp_path,
    family: str,
) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_literal_candidate_id_playbook(
        root / family / "named_logic.py",
        family,
        params="{}",
    )

    registry = discover_playbook_registry(root=root, repo_root=tmp_path)

    assert registry.ids(family) == (f"bad_{family}",)


def test_playbook_registry_rejects_ids_that_run_configs_cannot_reference(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(root / "indicators" / "bad.py", "indicators", "bad/id")

    with pytest.raises(PlaybookRegistryError, match="letters, numbers"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_playbook_registry_rejects_unsupported_stage(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(
        root / "indicators" / "bad_stage.py",
        "indicators",
        "bad_stage",
        stages=["signals"],
    )

    with pytest.raises(PlaybookRegistryError, match="unsupported stage"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_playbook_registry_rejects_label_family_manifest(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(root / "indicators" / "bad_label.py", "labels", "bad_label")

    with pytest.raises(PlaybookRegistryError, match="playbook family"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_playbook_registry_rejects_label_stage(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(
        root / "indicators" / "bad_label_stage.py",
        "indicators",
        "bad_label_stage",
        stages=["labels"],
    )

    with pytest.raises(PlaybookRegistryError, match="unsupported stage"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_playbook_registry_rejects_stale_label_family_files(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(root / "labels" / "stale.py", "labels", "stale")

    with pytest.raises(PlaybookRegistryError, match="unsupported playbook family"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_indicator_playbook_rejects_multiple_indicator_families(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    _write_playbook(
        root / "indicators" / "too_many.py",
        "indicators",
        "too_many",
        indicator_families=["ma", "rsi"],
    )

    with pytest.raises(PlaybookRegistryError, match="one indicator family"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def test_indicator_playbook_rejects_unknown_baseline_component(tmp_path) -> None:
    playbook_root = tmp_path / "research" / "playbooks"
    component_root = tmp_path / "research" / "components"
    _write_playbook(
        playbook_root / "indicators" / "baseline.py",
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


def test_playbook_registry_rejects_dangling_symlink_with_registry_error(tmp_path) -> None:
    root = tmp_path / "research" / "playbooks"
    link = root / "indicators" / "missing.py"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "missing.py")

    with pytest.raises(PlaybookRegistryError, match="symlink target does not exist"):
        discover_playbook_registry(root=root, repo_root=tmp_path)


def _write_playbook(
    path,
    family: str,
    playbook_id: str,
    *,
    stages: list[str] | None = None,
    indicator_families: list[str] | None = None,
    baseline_component_indicator_id: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": stages or [family],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_sweep_result.v1",
    }
    if family == "indicators":
        manifest["indicator_family"] = "ma"
        if indicator_families is not None:
            manifest["indicator_families"] = indicator_families
        if baseline_component_indicator_id is not None:
            manifest["baseline_component_indicator_id"] = baseline_component_indicator_id
    path.write_text(
        "# %% playbook overview\n"
        "# Registry fixture playbook selected by stable ID.\n"
        "# Source: synthetic Close data supplied by tests.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "from research.aegis_research.candidate_sweeps import candidate_id_from_params\n"
        "\n"
        "def run(_inputs):\n"
        '    """Return one fixture candidate with reproducible params."""\n'
        "    params = {'window': 5}\n"
        f"    candidate_id = candidate_id_from_params({playbook_id!r}, params)\n"
        "    return {"
        "'contract': 'aegis.playbook_sweep.v1', "
        "'kind': 'indicator_surface', "
        "'candidate_axis': [{'candidate_id': candidate_id, 'params': params}], "
        "'outputs': {'ma': 'not-materialized'}}\n"
    )


def _write_literal_candidate_id_playbook(path, family: str, *, params: str = "{'window': 5}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": family,
        "id": f"bad_{family}",
        "version": "1.0.0",
        "stages": [family],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_sweep_result.v1",
    }
    if family == "indicators":
        manifest["indicator_family"] = "ma"
    kind = "indicator_surface" if family == "indicators" else "strategy_axis"
    path.write_text(
        "# %% playbook overview\n"
        "# Bad fixture with hard-coded candidate ID.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "def run(_inputs):\n"
        '    """Return a candidate whose ID can drift from params."""\n'
        "    return {"
        "'contract': 'aegis.playbook_sweep.v1', "
        f"'kind': {kind!r}, "
        "'candidate_axis': [{'candidate_id': 'literal-5', 'params': " + params + "}]}\n"
    )

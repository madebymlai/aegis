from __future__ import annotations

from pathlib import Path


def test_active_cli_docs_use_aerd_contract() -> None:
    docs = Path("docs/vectorbt-scaffold.md").read_text()

    assert "aerd run <config>" in docs
    assert "aerd run --train" not in docs
    assert "aerd play" not in docs
    assert "aerd exp" not in docs
    assert "Both run configs require explicit config paths" in docs
    assert "| `execution_failure` | 10 |" in docs
    assert "aegis-research run" not in docs
    assert "python -m research.aegis_research.cli" not in docs


def test_active_docs_use_vbt_data_arrays_not_feature_map() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "data.arrays" in docs
    assert "arrays: [OHLCV" in docs
    assert "Data.features" in docs
    assert "DATA_ARRAY_SHORTCUTS" in docs
    assert "data.feature_map" not in docs


def test_model_plugin_docs_are_removed_from_active_surface() -> None:
    assert not Path("docs/model-plugins.md").exists()
    assert not Path("docs/examples/model_plugins").exists()


def test_component_and_playbook_docs_keep_yaml_inert_and_component_refs_direct() -> None:
    docs = "\n".join(
        [
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "strategy:\n  id:" in docs
    assert "indicators:\n  - id:" in docs
    assert "Source selectors" in docs
    assert "indicator `ids` batching" in docs
    assert "YAML never imports Python" in docs
    assert "arbitrary notebook paths" in docs
    assert "last-run refs" in docs
    assert "one indicator entry per component id" in docs
    assert "legacy historical artifacts" in docs


def test_active_docs_remove_labeler_contract() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "labeler:" not in docs
    assert "labeler: {id: ...}" not in docs
    assert "top-level `labeler`" not in docs
    assert "train.label" not in docs
    assert "research/playbooks/{labels,indicators,strategies}/" not in docs


def test_docs_examples_remove_train_notebooks() -> None:
    examples = "\n".join(
        path.read_text() for path in Path("docs/examples").rglob("*") if path.is_file()
    )

    assert "labeler" not in examples
    assert "train.label" not in examples
    assert "model_plugin" not in examples
    assert not Path("docs/examples/scaffold_experiment_walkthrough.ipynb").exists()


def test_docs_describe_composed_strategy_candidates_and_manual_promotion() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "complete composed strategy candidates" in docs
    assert "Component promotion uses persisted candidate rows" in docs
    assert "playbook_sweep_result.v1" in docs
    assert "candidate_grid.batch_size" not in docs
    assert "removed from the forward run contract" in docs
    assert "lock_id" in docs
    assert "candidate_id" in docs
    assert "best indicator" not in docs


def test_component_and_playbook_placeholders_point_to_examples() -> None:
    paths = [
        "research/components/indicators/README.md",
        "research/components/strategies/README.md",
        "research/playbooks/indicators/README.md",
        "research/playbooks/strategies/README.md",
    ]

    for path in paths:
        readme = Path(path).read_text()
        assert "docs/examples/" in readme
        assert "ignored by git" in readme
        assert "not secret management" in readme

    assert not Path("research/playbooks/labels/README.md").exists()

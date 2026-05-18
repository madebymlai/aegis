from __future__ import annotations

from pathlib import Path


def test_active_cli_docs_use_aerd_contract() -> None:
    docs = Path("docs/vectorbt-scaffold.md").read_text()

    assert "aerd play <config>" in docs
    assert "aerd run <config>" in docs
    assert "aerd train <config>" in docs
    assert "aerd exp defaults set <experiment-config>" in docs
    assert "New `play`, strategy `run`, and `train` lanes require explicit config paths" in docs
    assert "rejected` or `needs_more_evidence` report still exits `0`" in docs
    assert "| `execution_failure` | 10 |" in docs
    assert "aegis-research run" not in docs
    assert "python -m research.aegis_research.cli" not in docs


def test_model_plugin_docs_keep_yaml_inert_and_aerd_registry_explicit() -> None:
    docs = Path("docs/model-plugins.md").read_text()

    assert "Experiment YAML selects a stable `model.plugin_id`; it never imports Python code" in docs
    assert "aerd train" in docs
    assert "`aerd run` is reserved for promoted strategy sweeps" in docs


def test_component_and_playbook_docs_keep_yaml_inert_and_source_refs_explicit() -> None:
    docs = "\n".join(
        [
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "source: component" in docs
    assert "source: playbook" in docs
    assert "id: all" in docs
    assert "YAML never imports Python" in docs
    assert "arbitrary notebook paths" in docs
    assert "last-run refs" in docs
    assert "one indicator idea/family" in docs
    assert "exactly one component indicator ID" in docs


def test_component_and_playbook_placeholders_point_to_examples() -> None:
    paths = [
        "research/components/labels/README.md",
        "research/components/indicators/README.md",
        "research/components/strategies/README.md",
        "research/playbooks/labels/README.md",
        "research/playbooks/indicators/README.md",
        "research/playbooks/strategies/README.md",
    ]

    for path in paths:
        readme = Path(path).read_text()
        assert "docs/examples/" in readme
        assert "ignored by git" in readme
        assert "not secret management" in readme

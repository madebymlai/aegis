from __future__ import annotations

from pathlib import Path


def test_active_cli_docs_use_aerd_contract() -> None:
    docs = Path("docs/vectorbt-scaffold.md").read_text()

    assert "aerd run <experiment-config>" in docs
    assert "aerd exp defaults set <experiment-config>" in docs
    assert "An explicit config argument always wins" in docs
    assert "rejected` or `needs_more_evidence` report still exits `0`" in docs
    assert "| `execution_failure` | 10 |" in docs
    assert "aegis-research run" not in docs
    assert "python -m research.aegis_research.cli" not in docs


def test_model_plugin_docs_keep_yaml_inert_and_aerd_registry_explicit() -> None:
    docs = Path("docs/model-plugins.md").read_text()

    assert "Experiment YAML selects a stable `model.plugin_id`; it never imports Python code" in docs
    assert "the `aerd` CLI registers this default registry automatically" in docs

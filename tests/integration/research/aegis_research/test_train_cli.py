from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import RunStatus
from tests.support.research.aegis_research.model_plugin_fixtures import model_config_dict


def test_train_json_runs_existing_ml_pipeline_with_training_lane_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_label_component(tmp_path / "research/components/labels/fixlb.py")
    config_path = _write_config(tmp_path)

    assert cli.main(["run", "--train", str(config_path), "--json", "--run-id", "train-json-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["lane"] == "train"
    assert payload["evidence_type"] == "ml_training"
    assert payload["run"]["id"] == "train-json-run"
    assert payload["run"]["status"] == RunStatus.COMPLETED
    assert (tmp_path / "runs" / "train-json-run" / "manifest.json").is_file()


def test_train_requires_explicit_config_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "--train", "--json"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"


def test_train_rejects_run_artifact_source_refs_before_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "train.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "bad_train",
                "portfolio": {"entry_budget": 1.0},
                "train": {
                    "label": {
                        "source": "component",
                        "id": "missing",
                        "artifact_path": "runs/previous-run/strategy_run.json",
                    },
                    "model": {"source": "plugin", "id": "tests.sklearn_logistic"},
                },
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", "--train", str(path), "--json", "--run-id", "bad-train"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    assert "artifact_path" in json.loads(output.err)["error"]["message"]
    assert not (tmp_path / "runs" / "bad-train").exists()


def _write_config(tmp_path: Path, **overrides: Any) -> Path:
    model = model_config_dict(min_train_samples=1)
    config: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "train_contract",
        "output_dir": "runs",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "timeframe": "1D"},
        "portfolio": {"entry_budget": 1.0},
        "report": {"freq": "1D", "year_freq": "252D"},
        "train": {
            "label": {"source": "component", "id": "demo.fixlb"},
            "model": {
                "source": "plugin",
                "id": model["plugin_id"],
                "min_train_samples": model["min_train_samples"],
                "params": model["params"],
            },
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _write_label_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from research.aegis_research.config import LabelConfig\n"
        "from research.aegis_research.labels import build_label_result\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'labels', 'id': 'demo.fixlb', 'version': '1.0.0', "
        "'target_role': 'supervised_target', 'target_kind': 'binary_classification', "
        "'output_names': ['labels']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "def run(close, *, params):\n"
        "    return build_label_result(close, LabelConfig())\n"
    )

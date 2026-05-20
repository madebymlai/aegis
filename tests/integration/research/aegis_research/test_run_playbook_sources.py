from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import RunStatus


def test_run_cli_executes_repo_controlled_playbooks_by_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "playbook-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    artifact = json.loads((tmp_path / "runs" / "playbook-run" / "strategy_run.json").read_text())
    assert payload["status"] == "success"
    assert payload["lane"] == "run"
    assert artifact["strategy"]["source"] == "playbook"
    assert artifact["strategy"]["id"] == "ma_cross"
    assert artifact["strategy"]["consumes_runner_data"] is True
    assert artifact["strategy"]["data_binding"] == "strategy_inputs"
    assert artifact["data"]["strategy_consumed_runner_data"] is True
    assert artifact["data"]["strategy_data_binding"] == "strategy_inputs"
    assert artifact["indicators"][0]["source"] == "playbook"
    assert artifact["indicators"][0]["id"] == "ma_explore"
    assert artifact["leaderboard"]["summary"]["succeeded"] == 1
    assert artifact["leaderboard"]["rows"][0]["strategy_source"] == "playbook"
    assert artifact["leaderboard"]["rows"][0]["metric_authority"] == "aegis"


def test_run_cli_expands_all_playbook_indicators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_one.py", "indicators", "ma_one")
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_two.py", "indicators", "ma_two")
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        indicators=[{"source": "playbook", "ids": "all"}],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "playbook-all-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    artifact = json.loads(
        (tmp_path / "runs" / "playbook-all-run" / "strategy_run.json").read_text()
    )
    assert [item["id"] for item in artifact["indicators"]] == ["ma_one", "ma_two"]


def test_run_cli_unknown_playbook_fails_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="missing")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["status"] == "error"
    assert "unknown playbook id" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_run_cli_rejects_duplicate_expanded_playbook_indicators_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_one.py", "indicators", "ma_one")
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        indicators=[
            {"source": "playbook", "ids": "all"},
            {"source": "playbook", "ids": ["ma_one"]},
        ],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "duplicate-playbook"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "duplicate expanded playbook indicator id" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "duplicate-playbook").exists()


def test_run_cli_reports_failed_playbook_execution_on_run_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_failing_playbook(tmp_path / "research/playbooks/strategies/bad.py", "strategies", "bad")
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="bad")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "failed-playbook"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "failed-playbook" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert payload["run"]["status"] == RunStatus.FAILED
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_playbook_variant_without_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        include_params=False,
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "missing-params"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "missing-params" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "params must be a mapping" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_strategy_playbook_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        "strategies",
        "ma_cross",
        include_metrics=True,
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "metric-playbook"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "metric-playbook" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "metric or portfolio fields" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_indicator_playbook_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        include_metrics=True,
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "indicator-metrics"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "indicator-metrics" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "leaderboard metric fields" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_indicator_playbook_signal_or_portfolio_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        indicator_extra_fields={"portfolio": {"owner": "playbook"}},
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "indicator-fields"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "execution_failure"
    assert "signal, metric, or portfolio fields" in payload["error"]["message"]


def test_run_cli_rejects_strategy_playbook_variant_without_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        "strategies",
        "ma_cross",
        include_params=False,
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "missing-strategy-params"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "missing-strategy-params" / "manifest.json").read_text()
    )
    assert payload["error"]["category"] == "execution_failure"
    assert "params must be a mapping" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_unsafe_candidate_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        indicator_candidate_id="ma:bad",
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "unsafe-id"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "execution_failure"
    assert "candidate_id must contain only" in payload["error"]["message"]


def test_run_cli_rejects_duplicate_strategy_candidate_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        "strategies",
        "ma_cross",
        strategy_windows=[2, 2],
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "duplicate-strategy"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "execution_failure"
    assert "duplicate candidate" in payload["error"]["message"]


def test_run_cli_composes_indicator_and_strategy_playbook_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        "strategies",
        "ma_cross",
        strategy_windows=[2, 4],
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        indicator_windows=[2, 5],
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "composed-run"]) == 0

    output = capsys.readouterr()
    artifact = json.loads((tmp_path / "runs" / "composed-run" / "strategy_run.json").read_text())
    assert json.loads(output.out)["status"] == "success"
    assert artifact["composition"]["planned"]["indicator_context_count"] == 2
    assert artifact["composition"]["total_composed_candidates"] == 4
    assert artifact["leaderboard"]["summary"]["attempted"] == 4
    expected_ids = {
        "strategy:playbook:ma_cross:ma-cross-2+indicators:[playbook:ma_explore:ma-2]",
        "strategy:playbook:ma_cross:ma-cross-4+indicators:[playbook:ma_explore:ma-2]",
        "strategy:playbook:ma_cross:ma-cross-2+indicators:[playbook:ma_explore:ma-5]",
        "strategy:playbook:ma_cross:ma-cross-4+indicators:[playbook:ma_explore:ma-5]",
    }
    candidate_ids = {candidate["variant_id"] for candidate in artifact["candidates"]}
    assert candidate_ids == expected_ids
    assert set(artifact["signal_diagnostics"]["candidates"]) == expected_ids
    assert set(artifact["portfolio_diagnostics"]["candidates"]) == expected_ids
    row = artifact["leaderboard"]["rows"][0]
    assert row["metric_authority"] == "aegis"
    assert row["composed_candidate_id"].startswith("strategy:playbook:ma_cross:")
    assert row["strategy_params"]
    assert row["source_hash"]
    assert row["indicator_candidates"][0]["id"] == "ma_explore"
    assert row["indicator_candidates"][0]["candidate_id"].startswith("ma-")
    assert row["indicator_candidates"][0]["params"]
    assert row["indicator_candidates"][0]["source_hash"]


def test_run_cli_composes_indicator_playbook_candidates_with_component_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        indicator_windows=[2, 5],
    )
    _write_playbook_indicator_strategy_component(
        tmp_path / "research/components/strategies/uses_playbook_ma.py"
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="component",
        strategy_id="demo.uses_playbook_ma",
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-composed"]) == 0

    output = capsys.readouterr()
    artifact = json.loads(
        (tmp_path / "runs" / "component-composed" / "strategy_run.json").read_text()
    )
    assert json.loads(output.out)["status"] == "success"
    expected_ids = {
        "strategy:component:demo.uses_playbook_ma:demo.uses_playbook_ma"
        "+indicators:[playbook:ma_explore:ma-2]",
        "strategy:component:demo.uses_playbook_ma:demo.uses_playbook_ma"
        "+indicators:[playbook:ma_explore:ma-5]",
    }
    assert {candidate["variant_id"] for candidate in artifact["candidates"]} == expected_ids
    assert artifact["leaderboard"]["summary"]["attempted"] == 2
    assert artifact["composition"]["total_composed_candidates"] == 2


def test_run_cli_rejects_partially_consumed_indicator_playbook_axes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_single_indicator_strategy_playbook(
        tmp_path / "research/playbooks/strategies/ma_one_only.py"
    )
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_one.py", "indicators", "ma_one")
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_two.py", "indicators", "ma_two")
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_one_only",
        indicators=[{"source": "playbook", "ids": ["ma_one", "ma_two"]}],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "partial-consumption"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "playbook:ma_two" in payload["error"]["message"]


def test_run_cli_rejects_indicator_membership_check_as_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_outputs_membership_strategy_playbook(
        tmp_path / "research/playbooks/strategies/check_outputs.py"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="check_outputs",
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "membership-only"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "did not consume selected indicator playbook axes" in payload["error"]["message"]


def test_run_cli_rejects_unused_indicator_playbook_axis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ignore_indicators.py",
        "strategies",
        "ignore_indicators",
        consume_indicators=False,
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ignore_indicators",
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "unused-axis"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "unused-axis" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "did not consume selected indicator playbook axes" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_does_not_write_completed_strategy_artifact_for_partial_leaderboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_no_trade_strategy_playbook(tmp_path / "research/playbooks/strategies/no_trades.py")
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="no_trades",
        ranking_metric="win_rate_pct",
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "partial-leaderboard"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "partial-leaderboard" / "manifest.json").read_text()
    )
    assert payload["error"]["category"] == "execution_failure"
    assert "complete leaderboard" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert not (tmp_path / "runs" / "partial-leaderboard" / "strategy_run.json").exists()


def test_run_cli_accepts_empty_playbook_candidate_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        params={},
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "empty-params"]) == 0

    output = capsys.readouterr()
    artifact = json.loads((tmp_path / "runs" / "empty-params" / "strategy_run.json").read_text())
    assert json.loads(output.out)["status"] == "success"
    assert artifact["leaderboard"]["rows"][0]["indicator_candidates"][0]["params"] == {}


def test_run_cli_accepts_empty_strategy_candidate_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        "strategies",
        "ma_cross",
        params={},
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "empty-strategy-params"]) == 0

    output = capsys.readouterr()
    artifact = json.loads(
        (tmp_path / "runs" / "empty-strategy-params" / "strategy_run.json").read_text()
    )
    assert json.loads(output.out)["status"] == "success"
    assert artifact["leaderboard"]["rows"][0]["strategy_params"] == {}


def test_run_cli_rejects_playbook_that_does_not_support_requested_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/labels_only.py",
        "strategies",
        "labels_only",
        stages=["labels"],
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="labels_only")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "does not support strategies" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_playbook_roots_ignore_local_notebooks_except_readme_placeholders() -> None:
    for family in ("labels", "indicators", "strategies"):
        assert Path(f"research/playbooks/{family}/README.md").is_file()
        ignored_notebook = pytest.importorskip("subprocess").run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "--quiet",
                f"research/playbooks/{family}/local.py",
            ],
            check=False,
        )
        ignored_readme = pytest.importorskip("subprocess").run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "--quiet",
                f"research/playbooks/{family}/README.md",
            ],
            check=False,
        )

        assert ignored_notebook.returncode == 0
        assert ignored_readme.returncode == 1


def _write_run_config(
    tmp_path: Path,
    *,
    strategy_source: str,
    strategy_id: str,
    indicators: list[dict[str, object]] | None = None,
    ranking_metric: str = "total_return_pct",
) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "run_playbook_source_test",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN"],
                    "rows": 80,
                    "arrays": ["OHLCV"],
                },
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"source": strategy_source, "id": strategy_id},
                "indicators": indicators
                if indicators is not None
                else [{"source": "playbook", "ids": ["ma_explore"]}],
                "ranking": {"metric": ranking_metric, "direction": "desc"},
            },
            sort_keys=False,
        )
    )
    return path


def _write_playbook(
    path: Path,
    family: str,
    playbook_id: str,
    *,
    stages: list[str] | None = None,
    include_params: bool = True,
    include_metrics: bool = False,
    consume_indicators: bool = True,
    indicator_windows: list[int] | None = None,
    strategy_windows: list[int] | None = None,
    params: dict[str, object] | None = None,
    indicator_candidate_id: str | None = None,
    strategy_variant_id: str | None = None,
    indicator_extra_fields: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": stages or [family],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    if family == "indicators":
        manifest["indicator_family"] = "ma"
    if family == "strategies":
        windows = strategy_windows or [3]
        consume_source = (
            "    indicator_outputs = ["
            "value['outputs']['ma'] for key, value in inputs.indicators.items() "
            "if key.startswith('playbook:')"
            "]\n"
            "    if indicator_outputs:\n"
            "        average = sum(indicator_outputs) / len(indicator_outputs)\n"
            "    else:\n"
            "        average = close.rolling(3).mean().bfill()\n"
            if consume_indicators
            else "    average = close.rolling(3).mean().bfill()\n"
        )
        records_source = "\n".join(
            _strategy_record_source(
                window,
                include_params=include_params,
                include_metrics=include_metrics,
                params=params,
                variant_id=strategy_variant_id,
            )
            for window in windows
        )
        body = (
            "def run(inputs):\n"
            '    """Generate moving-average crossover candidates for central scoring."""\n'
            "    close = inputs.data.feature('Close')\n"
            f"{consume_source}"
            "    records = []\n"
            f"{records_source}\n"
            "    return {'variant_records': records}\n"
        )
    else:
        windows = indicator_windows or [5]
        records_source = "\n".join(
            _indicator_record_source(
                window,
                include_params=include_params,
                include_metrics=include_metrics,
                params=params,
                candidate_id=indicator_candidate_id,
                extra_fields=indicator_extra_fields,
            )
            for window in windows
        )
        body = (
            "def run(data):\n"
            '    """Return fixture indicator candidates for playbook source tests."""\n'
            "    close = data.feature('Close')\n"
            "    records = []\n"
            f"{records_source}\n"
            "    return {'variant_records': records}\n"
        )
    path.write_text(
        "# %% playbook overview\n"
        "# Integration fixture playbook selected by stable ID.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n" + body
    )


def _strategy_record_source(
    window: int,
    *,
    include_params: bool,
    include_metrics: bool,
    params: dict[str, object] | None,
    variant_id: str | None,
) -> str:
    metrics_source = "'metrics': {'total_return_pct': 1.5}, " if include_metrics else ""
    params_value = {"window": window} if params is None else params
    params_source = f"'params': {params_value!r}, " if include_params else ""
    record_id = variant_id or f"ma-cross-{window}"
    return (
        "    records.append({"
        f"'variant_id': {record_id!r}, "
        f"{params_source}"
        f"{metrics_source}"
        "'entries': (close > average).fillna(False), "
        "'exits': (close < average).fillna(False)})"
    )


def _indicator_record_source(
    window: int,
    *,
    include_params: bool,
    include_metrics: bool,
    params: dict[str, object] | None,
    candidate_id: str | None,
    extra_fields: dict[str, object] | None,
) -> str:
    metrics_source = "'metrics': {'total_return_pct': 1.5}, " if include_metrics else ""
    params_value = {"window": window} if params is None else params
    params_source = f"'params': {params_value!r}, " if include_params else ""
    extra_source = "".join(
        f"{key!r}: {value!r}, " for key, value in (extra_fields or {}).items()
    )
    record_id = candidate_id or f"ma-{window}"
    return (
        "    ma = close.rolling("
        f"{window}"
        ").mean().bfill()\n"
        "    records.append({"
        f"'candidate_id': {record_id!r}, "
        f"{params_source}"
        f"{metrics_source}"
        f"{extra_source}"
        "'outputs': {'ma': ma}})"
    )


def _write_single_indicator_strategy_playbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": "strategies",
        "id": "ma_one_only",
        "version": "1.0.0",
        "stages": ["strategies"],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Strategy fixture that consumes only one indicator playbook axis.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "def run(inputs):\n"
        '    """Use only ma_one so unused-axis validation can fail."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    ma = inputs.indicators['playbook:ma_one']['outputs']['ma']\n"
        "    return {'variant_records': [{'variant_id': 'uses-ma-one', "
        "'params': {}, 'entries': (close > ma).fillna(False), "
        "'exits': (close < ma).fillna(False)}]}\n"
    )


def _write_outputs_membership_strategy_playbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": "strategies",
        "id": "check_outputs",
        "version": "1.0.0",
        "stages": ["strategies"],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Strategy fixture that checks membership without consuming output frames.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "def run(inputs):\n"
        '    """Check output availability without using indicator values."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    _has_outputs = 'outputs' in inputs.indicators['playbook:ma_explore']\n"
        "    average = close.rolling(3).mean().bfill()\n"
        "    return {'variant_records': [{'variant_id': 'membership-only', "
        "'params': {}, 'entries': (close > average).fillna(False), "
        "'exits': (close < average).fillna(False)}]}\n"
    )


def _write_no_trade_strategy_playbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": "strategies",
        "id": "no_trades",
        "version": "1.0.0",
        "stages": ["strategies"],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Strategy fixture that emits no trades for unavailable win-rate metrics.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "def run(inputs):\n"
        '    """Consume the selected indicator and intentionally emit no trades."""\n'
        "    ma = inputs.indicators['playbook:ma_explore']['outputs']['ma']\n"
        "    signals = ma.notna() & False\n"
        "    return {'variant_records': [{'variant_id': 'no-trades', "
        "'params': {}, 'entries': signals, 'exits': signals}]}\n"
    )


def _write_playbook_indicator_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture consuming an indicator playbook output.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.uses_playbook_ma', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'signal_outputs': ['entries', 'exits'], 'owns_portfolio': False}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Generate signals from the selected playbook moving average."""\n'
        "    ma = bundle.indicators['playbook:ma_explore']['outputs']['ma']\n"
        "    close = bundle.data.feature('Close')\n"
        "    entries = close > ma\n"
        "    exits = close < ma\n"
        "    return {'entries': entries.fillna(False), 'exits': exits.fillna(False)}\n"
    )


def _write_failing_playbook(path: Path, family: str, playbook_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": [family],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Integration fixture playbook that fails during callable execution.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "def run(_inputs):\n"
        '    """Raise a deterministic fixture error for failure-path tests."""\n'
        "    raise RuntimeError('boom token=secret')\n"
    )

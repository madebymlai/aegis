from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli, strategy_runs
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import RunStatus


def test_run_cli_executes_repo_controlled_playbooks_by_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py"
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
    )

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
    assert artifact["strategy"]["data_binding"] == "strategy_sweep_inputs"
    assert artifact["data"]["strategy_consumed_runner_data"] is True
    assert artifact["data"]["strategy_data_binding"] == "strategy_sweep_inputs"
    assert artifact["indicators"][0]["source"] == "playbook"
    assert artifact["indicators"][0]["id"] == "ma_explore"
    assert artifact["leaderboard"]["summary"]["succeeded"] == 2
    assert artifact["leaderboard"]["rows"][0]["strategy_source"] == "playbook"
    assert artifact["leaderboard"]["rows"][0]["metric_source"] == "central_portfolio"


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
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="bad")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "failed-playbook"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "failed-playbook" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert payload["run"]["status"] == RunStatus.FAILED
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_legacy_playbook_result_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_batched_indicator_playbook(tmp_path / "research/playbooks/indicators/ma_explore.py")
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "legacy-rejected"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "legacy-rejected" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "playbook_sweep_result.v1" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_executes_playbook_strategy_sweep_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-run"]) == 0

    output = capsys.readouterr()
    artifact = json.loads((tmp_path / "runs" / "batched-run" / "strategy_run.json").read_text())
    manifest = json.loads((tmp_path / "runs" / "batched-run" / "manifest.json").read_text())
    assert json.loads(output.out)["status"] == "success"
    assert artifact["schema_version"] == "strategy_run.v3"
    assert artifact["strategy"]["result_contract"] == "aegis.playbook_sweep.v1"
    assert artifact["composition"]["planned"]["indicator_preflight"]["indicator_context_count"] == 2
    assert artifact["composition"]["planned"]["strategy_candidate_count"] == 2
    assert artifact["composition"]["planned"]["total_composed_candidates"] == 4
    assert artifact["composition"]["planned"]["batch_count"] == 2
    assert artifact["leaderboard"]["summary"]["attempted"] == 4
    candidate_ids = {candidate["variant_id"] for candidate in artifact["candidates"]}
    assert candidate_ids == {
        "strategy:playbook:ma_cross:fast-0+indicators:[playbook:ma_explore:ma-2]",
        "strategy:playbook:ma_cross:slow-0.01+indicators:[playbook:ma_explore:ma-2]",
        "strategy:playbook:ma_cross:fast-0+indicators:[playbook:ma_explore:ma-5]",
        "strategy:playbook:ma_cross:slow-0.01+indicators:[playbook:ma_explore:ma-5]",
    }
    row = artifact["leaderboard"]["rows"][0]
    composed = artifact["catalogs"]["composed_candidates"][row["composed_candidate_id"]]
    assert row["metric_source"] == "central_portfolio"
    assert row["strategy_candidate_ref"] == composed["strategy_candidate_ref"]
    assert row["indicator_candidate_refs"] == composed["indicator_candidate_refs"]
    assert row["metric_ref"] == composed["metric_ref"]
    assert row["chunk_ref"] == composed["chunk_ref"]
    assert row["strategy_params"]
    assert row["indicator_candidates"][0]["params"]
    assert artifact["catalogs"]["strategy_candidates"][row["strategy_candidate_ref"]]["params"]
    assert artifact["catalogs"]["indicator_candidates"][row["indicator_candidate_refs"][0]]["params"]
    assert artifact["catalogs"]["metrics"][row["metric_ref"]]["metric_scope"] == "shared_cash_group"
    assert artifact["catalogs"]["chunks"][row["chunk_ref"]]["status"] == "succeeded"
    assert set(artifact["candidates"][0]) == {
        "variant_id",
        "composed_candidate_id",
        "strategy_candidate_ref",
        "indicator_candidate_refs",
        "metric_ref",
        "chunk_ref",
        "metric_source",
    }
    strategy_artifact = next(item for item in manifest["artifacts"] if item["id"] == "strategy.run")
    assert strategy_artifact["shape"] | {
        "leaderboard_rows": 4,
        "candidate_count": 4,
        "indicator_candidate_count": 2,
        "strategy_candidate_count": 2,
        "composed_candidate_count": 4,
        "chunk_count": 2,
        "metric_count": 4,
    } == strategy_artifact["shape"]
    assert {item["batch_index"] for item in artifact["signal_diagnostics"]["candidates"].values()} == {
        0,
        1,
    }
    assert set(artifact["portfolio_diagnostics"]["chunks"]) == {"batch-000000", "batch-000001"}
    first_portfolio_candidate = next(iter(artifact["portfolio_diagnostics"]["candidates"].values()))
    assert set(first_portfolio_candidate) == {
        "batch_index",
        "chunk_ref",
    }


def test_run_cli_executes_playbook_strategy_sweep_with_rolling_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(tmp_path / "research/playbooks/indicators/ma_explore.py")
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
        split=_rolling_split_config(),
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "rolling-playbook"]) == 0

    output = capsys.readouterr()
    artifact = json.loads((tmp_path / "runs" / "rolling-playbook" / "strategy_run.json").read_text())
    manifest = json.loads((tmp_path / "runs" / "rolling-playbook" / "manifest.json").read_text())
    assert json.loads(output.out)["status"] == "success"
    assert artifact["split"]["method"] == "from_rolling"
    assert artifact["leaderboard"]["schema_version"] == "split_run_leaderboard.v1"
    assert artifact["leaderboard"]["summary"]["attempted_splits"] == artifact["split"]["n_splits"]
    assert artifact["leaderboard"]["rows"][0]["metric_source"] == "central_portfolio"
    assert artifact["leaderboard"]["rows"][0]["selected_split_count"] >= 1
    assert {record["set"] for record in artifact["split_metrics"]} == {"selection", "held_out"}
    assert sum(1 for record in artifact["split_metrics"] if record["set"] == "held_out") == artifact[
        "split"
    ]["n_splits"]
    assert {record["native_set"] for record in artifact["split_metrics"]} == {
        "selection",
        "held_out",
    }
    assert artifact["catalogs"]["metrics"] == {}
    strategy_artifact = next(item for item in manifest["artifacts"] if item["id"] == "strategy.run")
    assert strategy_artifact["status"] == "completed"
    assert strategy_artifact["shape"]["split_count"] == artifact["split"]["n_splits"]
    assert strategy_artifact["shape"]["split_metric_count"] == len(artifact["split_metrics"])


def test_run_cli_batches_playbook_strategy_sweep_final_smaller_candidate_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5, 8],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 4},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-final-chunk"]) == 0

    output = capsys.readouterr()
    artifact = json.loads(
        (tmp_path / "runs" / "batched-final-chunk" / "strategy_run.json").read_text()
    )
    assert json.loads(output.out)["status"] == "success"
    assert artifact["composition"]["planned"]["total_composed_candidates"] == 6
    assert artifact["composition"]["planned"]["batch_count"] == 2
    batch_indexes = [
        item["batch_index"] for item in artifact["signal_diagnostics"]["candidates"].values()
    ]
    assert batch_indexes.count(0) == 4
    assert batch_indexes.count(1) == 2


def test_run_cli_rejects_non_batched_indicator_for_batched_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "non-batched-indicator"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "non-batched-indicator" / "manifest.json").read_text()
    )
    assert payload["error"]["category"] == "execution_failure"
    assert "result_schema" in payload["error"]["message"]
    assert "playbook_sweep_result.v1" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert not (tmp_path / "runs" / "non-batched-indicator" / "strategy_run.json").exists()


def test_run_cli_rejects_batched_materializer_that_omits_requested_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        signal_mode="omit_last",
    )
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-omits"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "batched-omits" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "candidate axis mismatch" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["evidence"]["composition"]["total_composed_candidates"] == 4
    assert manifest["evidence"]["chunks"]["chunks"][0]["status"] == "failed"
    assert manifest["evidence"]["chunks"]["chunks"][0]["error"]["stage"] == "materialize_signals"
    assert not (tmp_path / "runs" / "batched-omits" / "strategy_run.json").exists()


def test_run_cli_rejects_batched_materializer_that_adds_unrequested_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        signal_mode="extra_unrequested",
    )
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-extra"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "batched-extra" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "candidate axis mismatch" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["evidence"]["composition"]["total_composed_candidates"] == 4
    assert manifest["evidence"]["chunks"]["chunks"][0]["status"] == "failed"
    assert manifest["evidence"]["chunks"]["chunks"][0]["error"]["stage"] == "materialize_signals"
    assert not (tmp_path / "runs" / "batched-extra" / "strategy_run.json").exists()


def test_run_cli_records_failed_batched_chunk_candidate_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        signal_mode="fail_second_batch",
    )
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-chunk-fails"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-chunk-fails" / "manifest.json").read_text()
    )
    chunks = manifest["evidence"]["chunks"]["chunks"]
    assert payload["error"]["category"] == "execution_failure"
    assert "second batch failed intentionally" in payload["error"]["message"]
    assert chunks[0]["status"] == "succeeded"
    assert chunks[1]["status"] == "failed"
    assert chunks[1]["error"]["stage"] == "materialize_signals"
    assert chunks[1]["candidate_ids"] == [
        "strategy:playbook:ma_cross:fast-0+indicators:[playbook:ma_explore:ma-5]",
        "strategy:playbook:ma_cross:slow-0.01+indicators:[playbook:ma_explore:ma-5]",
    ]
    assert not (tmp_path / "runs" / "batched-chunk-fails" / "strategy_run.json").exists()


def test_run_cli_rejects_batched_strategy_that_does_not_consume_indicator_axis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        consume_indicators=False,
    )
    _write_batched_indicator_playbook(tmp_path / "research/playbooks/indicators/ma_explore.py")
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-unconsumed"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-unconsumed" / "manifest.json").read_text()
    )
    chunks = manifest["evidence"]["chunks"]["chunks"]
    assert payload["error"]["category"] == "execution_failure"
    assert "did not consume selected indicator playbook axes" in payload["error"]["message"]
    assert chunks[0]["status"] == "failed"
    assert chunks[0]["error"]["stage"] == "indicator_consumption_validation"
    assert not (tmp_path / "runs" / "batched-unconsumed" / "strategy_run.json").exists()


def test_run_cli_records_batched_portfolio_simulation_failure_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )

    def fail_portfolio_batch(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("portfolio batch failed intentionally")

    monkeypatch.setattr(strategy_runs, "simulate_portfolio_batch", fail_portfolio_batch)
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-portfolio-fails"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-portfolio-fails" / "manifest.json").read_text()
    )
    chunk = manifest["evidence"]["chunks"]["chunks"][0]
    assert payload["error"]["category"] == "execution_failure"
    assert "portfolio batch failed intentionally" in payload["error"]["message"]
    assert chunk["status"] == "failed"
    assert chunk["error"]["stage"] == "portfolio_simulation"
    assert chunk["candidate_ids"] == [
        "strategy:playbook:ma_cross:fast-0+indicators:[playbook:ma_explore:ma-2]",
        "strategy:playbook:ma_cross:slow-0.01+indicators:[playbook:ma_explore:ma-2]",
    ]
    assert not (tmp_path / "runs" / "batched-portfolio-fails" / "strategy_run.json").exists()


def test_run_cli_preserves_partial_split_artifact_after_later_chunk_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(tmp_path / "research/playbooks/indicators/ma_explore.py")
    original_simulate_portfolio_batch = strategy_runs.simulate_portfolio_batch

    def fail_second_candidate_batch(*args: object, **kwargs: object) -> object:
        entries = args[1]
        candidate_id = str(entries.columns.get_level_values("candidate_id")[0])
        if ":slow-" in candidate_id:
            raise RuntimeError("split portfolio batch failed intentionally")
        return original_simulate_portfolio_batch(*args, **kwargs)

    monkeypatch.setattr(
        strategy_runs,
        "simulate_portfolio_batch",
        fail_second_candidate_batch,
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 1},
        split=_rolling_split_config(),
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "split-partial"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "split-partial" / "manifest.json").read_text())
    artifact = json.loads((tmp_path / "runs" / "split-partial" / "strategy_run.json").read_text())
    strategy_artifact = next(item for item in manifest["artifacts"] if item["id"] == "strategy.run")
    chunks = manifest["evidence"]["chunks"]["chunks"]
    assert payload["error"]["category"] == "execution_failure"
    assert "split portfolio batch failed intentionally" in payload["error"]["message"]
    assert chunks[0]["status"] == "succeeded"
    assert chunks[1]["status"] == "failed"
    assert chunks[1]["error"]["stage"] == "split_portfolio_simulation"
    assert strategy_artifact["status"] == "partial"
    assert strategy_artifact["shape"]["split_metric_count"] == len(artifact["split_metrics"])
    assert artifact["split_metrics"]
    assert artifact["leaderboard"]["summary"]["partial_leaderboard"] is True


def test_run_cli_records_batched_metric_extraction_failure_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )

    def fail_metric_extraction(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("metric extraction failed intentionally")

    monkeypatch.setattr(
        strategy_runs,
        "portfolio_metrics_by_candidate_group",
        fail_metric_extraction,
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-metrics-fail"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-metrics-fail" / "manifest.json").read_text()
    )
    chunk = manifest["evidence"]["chunks"]["chunks"][0]
    assert payload["error"]["category"] == "execution_failure"
    assert "metric extraction failed intentionally" in payload["error"]["message"]
    assert chunk["status"] == "failed"
    assert chunk["error"]["stage"] == "metric_extraction"
    assert chunk["candidate_ids"] == [
        "strategy:playbook:ma_cross:fast-0+indicators:[playbook:ma_explore:ma-2]",
        "strategy:playbook:ma_cross:slow-0.01+indicators:[playbook:ma_explore:ma-2]",
    ]
    assert not (tmp_path / "runs" / "batched-metrics-fail" / "strategy_run.json").exists()


def test_run_cli_rejects_over_budget_batched_composed_candidates_with_manifest_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"max_candidates": 3, "batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-over-budget"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-over-budget" / "manifest.json").read_text()
    )
    assert payload["error"]["category"] == "execution_failure"
    assert "above candidate_grid.max_candidates=3" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["evidence"]["composition"]["total_composed_candidates"] == 4
    assert manifest["evidence"]["composition"]["batch_count"] == 2
    assert "chunks" not in manifest["evidence"]
    assert not (tmp_path / "runs" / "batched-over-budget" / "strategy_run.json").exists()


def test_run_cli_rejects_over_budget_batched_execution_batch_with_manifest_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"max_estimated_cells": 500, "batch_size": 4},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-exec-budget"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-exec-budget" / "manifest.json").read_text()
    )
    execution_preflight = manifest["evidence"]["composition"]["execution_preflight"]
    assert payload["error"]["category"] == "execution_failure"
    assert "candidate_grid.max_estimated_cells=500" in payload["error"]["message"]
    assert "candidate_grid.batch_size" in payload["error"]["message"]
    assert execution_preflight["batch_candidate_count"] == 4
    assert execution_preflight["estimated_cells"] == 1600
    assert "chunks" not in manifest["evidence"]
    assert not (tmp_path / "runs" / "batched-exec-budget" / "strategy_run.json").exists()


def test_run_cli_persists_batched_indicator_preflight_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"max_estimated_cells": 1},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-preflight"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-preflight" / "manifest.json").read_text()
    )
    preflight = manifest["evidence"]["composition"]["indicator_preflight"]
    assert payload["error"]["category"] == "execution_failure"
    assert "candidate_grid.max_estimated_cells=1" in payload["error"]["message"]
    assert preflight["indicator_context_count"] == 2
    assert preflight["estimated_cells"] == 160
    assert not (tmp_path / "runs" / "batched-preflight" / "strategy_run.json").exists()


def test_run_cli_persists_batched_indicator_count_preflight_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_batched_strategy_playbook(tmp_path / "research/playbooks/strategies/ma_cross.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        windows=[2, 5],
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        candidate_grid={"max_candidates": 1},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "batched-count-preflight"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads(
        (tmp_path / "runs" / "batched-count-preflight" / "manifest.json").read_text()
    )
    preflight = manifest["evidence"]["composition"]["indicator_preflight"]
    assert payload["error"]["category"] == "execution_failure"
    assert "candidate_grid.max_candidates=1" in payload["error"]["message"]
    assert preflight["indicator_context_count"] == 2
    assert preflight["limits"]["max_candidates"] == 1
    assert not (tmp_path / "runs" / "batched-count-preflight" / "strategy_run.json").exists()


def test_run_cli_rejects_playbook_indicators_with_component_strategy(
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

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-composed"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "cannot enter the component runner" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "component-composed").exists()


def test_run_cli_does_not_write_completed_strategy_artifact_for_partial_leaderboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_no_trade_strategy_playbook(tmp_path / "research/playbooks/strategies/no_trades.py")
    _write_batched_indicator_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py"
    )
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="no_trades",
        ranking_metric="win_rate",
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


def test_run_cli_rejects_playbook_that_does_not_support_requested_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/indicators_only.py",
        "strategies",
        "indicators_only",
        stages=["indicators"],
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="indicators_only")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "does not support strategies" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_playbook_roots_ignore_local_notebooks_except_readme_placeholders() -> None:
    assert not Path("research/playbooks/labels/README.md").exists()

    for family in ("indicators", "strategies"):
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
    ranking_metric: str = "total_return",
    candidate_grid: dict[str, object] | None = None,
    split: dict[str, object] | None = None,
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
                **({"candidate_grid": candidate_grid} if candidate_grid is not None else {}),
                **({"split": split} if split is not None else {}),
            },
            sort_keys=False,
        )
    )
    return path


def _rolling_split_config() -> dict[str, object]:
    return {
        "method": "from_rolling",
        "params": {
            "length": 20,
            "offset": 20,
            "split": 0.5,
            "set_labels": ["selection", "held_out"],
        },
        "max_splits": 5,
    }


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


def _write_batched_indicator_playbook(path: Path, *, windows: list[int] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    windows = windows or [2]
    manifest = {
        "family": "indicators",
        "id": "ma_explore",
        "version": "1.0.0",
        "stages": ["indicators"],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_sweep_result.v1",
        "indicator_family": "ma",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Sweep contract fixture for record-runner rejection.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "import pandas as pd\n"
        "\n"
        "def run(data):\n"
        '    """Return a forward batched indicator contract."""\n'
        "    close = data.feature('Close')\n"
        f"    candidate_ids = {[f'ma-{window}' for window in windows]!r}\n"
        f"    windows = {windows!r}\n"
        "    frames = []\n"
        "    for candidate_id, window in zip(candidate_ids, windows):\n"
        "        frame = close.rolling(window).mean().bfill()\n"
        "        frame.columns = pd.MultiIndex.from_product(\n"
        "            [[candidate_id], list(close.columns)], names=['candidate_id', 'symbol']\n"
        "        )\n"
        "        frames.append(frame)\n"
        "    ma = pd.concat(frames, axis=1)\n"
        "    return {\n"
        "        'contract': 'aegis.playbook_sweep.v1',\n"
        "        'kind': 'indicator_surface',\n"
        "        'candidate_axis': [\n"
        "            {'candidate_id': candidate_id, 'params': {'window': window}}\n"
        "            for candidate_id, window in zip(candidate_ids, windows)\n"
        "        ],\n"
        "        'outputs': {'ma': ma},\n"
        "    }\n"
    )


def _write_batched_strategy_playbook(
    path: Path,
    *,
    signal_mode: str = "requested",
    consume_indicators: bool = True,
) -> None:
    if signal_mode not in {"requested", "omit_last", "extra_unrequested", "fail_second_batch"}:
        raise ValueError(f"unknown batched strategy signal mode: {signal_mode}")
    path.parent.mkdir(parents=True, exist_ok=True)
    indicator_binding_source = (
        "    indicators = inputs.indicators['playbook:ma_explore']\n"
        "    ma_surface = indicators['outputs']['ma']\n"
        if consume_indicators
        else "    ma_surface = close.rolling(2).mean().bfill()\n"
    )
    indicator_frame_source = (
        "            indicator_id = candidate.indicators[0].candidate_id\n"
        "            ma = ma_surface.xs(indicator_id, level='candidate_id', axis=1, drop_level=True)\n"
        "            ma.columns = close.columns\n"
        if consume_indicators
        else "            ma = ma_surface.copy()\n"
    )
    manifest = {
        "family": "strategies",
        "id": "ma_cross",
        "version": "1.0.0",
        "stages": ["strategies"],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_sweep_result.v1",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Strategy sweep fixture for candidate-grid tests.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "import pandas as pd\n"
        "from research.aegis_research.candidate_sweeps import candidate_id_from_params\n"
        "\n"
        "def run(inputs):\n"
        '    """Discover strategy params and materialize requested signal batches."""\n'
        "    close = inputs.data.feature('Close')\n"
        f"{indicator_binding_source}"
        "    strategy_candidates = []\n"
        "    for name, threshold in (('fast', 0.0), ('slow', 0.01)):\n"
        "        params = {'threshold': threshold}\n"
        "        strategy_candidates.append({\n"
        "            'candidate_id': candidate_id_from_params(name, params),\n"
        "            'params': params,\n"
        "        })\n"
        "    materialize_call_count = 0\n"
        "\n"
        "    def materialize_signals(request):\n"
        "        nonlocal materialize_call_count\n"
        "        materialize_call_count += 1\n"
        "        def candidate_signal_frames(candidate, output_candidate_id):\n"
        f"{indicator_frame_source}"
        "            threshold = candidate.strategy.params['threshold']\n"
        "            entries = close > (ma * (1 + threshold))\n"
        "            exits = close < ma\n"
        "            entries.columns = pd.MultiIndex.from_product(\n"
        "                [[output_candidate_id], list(close.columns)], names=['candidate_id', 'symbol']\n"
        "            )\n"
        "            exits.columns = pd.MultiIndex.from_product(\n"
        "                [[output_candidate_id], list(close.columns)], names=['candidate_id', 'symbol']\n"
        "            )\n"
        "            return entries, exits\n"
        "\n"
        "        entry_frames = []\n"
        "        exit_frames = []\n"
        f"        signal_mode = {signal_mode!r}\n"
        "        if signal_mode == 'fail_second_batch' and materialize_call_count == 2:\n"
        "            raise RuntimeError('second batch failed intentionally')\n"
        "        candidates = list(request.candidates)\n"
        "        if signal_mode == 'omit_last':\n"
        "            candidates = candidates[:-1]\n"
        "        for candidate in candidates:\n"
        "            entries, exits = candidate_signal_frames(candidate, candidate.candidate_id)\n"
        "            entry_frames.append(entries)\n"
        "            exit_frames.append(exits)\n"
        "        if signal_mode == 'extra_unrequested':\n"
        "            entries, exits = candidate_signal_frames(request.candidates[0], 'unexpected')\n"
        "            entry_frames.append(entries)\n"
        "            exit_frames.append(exits)\n"
        "        return {\n"
        "            'contract': 'aegis.playbook_sweep.v1',\n"
        "            'kind': 'strategy_signals',\n"
        "            'entries': pd.concat(entry_frames, axis=1),\n"
        "            'exits': pd.concat(exit_frames, axis=1),\n"
        "        }\n"
        "\n"
        "    return {\n"
        "        'contract': 'aegis.playbook_sweep.v1',\n"
        "        'kind': 'strategy_axis',\n"
        "        'candidate_axis': strategy_candidates,\n"
        "        'materialize_signals': materialize_signals,\n"
        "    }\n"
    )


def _strategy_record_source(
    window: int,
    *,
    include_params: bool,
    include_metrics: bool,
    params: dict[str, object] | None,
    variant_id: str | None,
) -> str:
    metrics_source = "'metrics': {'total_return': 1.5}, " if include_metrics else ""
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
    metrics_source = "'metrics': {'total_return': 1.5}, " if include_metrics else ""
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
        "result_schema": "playbook_sweep_result.v1",
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
        "import pandas as pd\n"
        "\n"
        "def run(inputs):\n"
        '    """Consume the selected indicator and intentionally emit no trades."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    ma_surface = inputs.indicators['playbook:ma_explore']['outputs']['ma']\n"
        "\n"
        "    def materialize_signals(request):\n"
        "        frames = []\n"
        "        for candidate in request.candidates:\n"
        "            indicator_id = candidate.indicators[0].candidate_id\n"
        "            ma = ma_surface.xs(indicator_id, level='candidate_id', axis=1, drop_level=True)\n"
        "            signals = (ma.notna() & False).astype(bool)\n"
        "            signals.columns = pd.MultiIndex.from_product(\n"
        "                [[candidate.candidate_id], list(close.columns)], names=['candidate_id', 'symbol']\n"
        "            )\n"
        "            frames.append(signals)\n"
        "        signal_frame = pd.concat(frames, axis=1)\n"
        "        return {\n"
        "            'contract': 'aegis.playbook_sweep.v1',\n"
        "            'kind': 'strategy_signals',\n"
        "            'entries': signal_frame,\n"
        "            'exits': signal_frame,\n"
        "        }\n"
        "\n"
        "    return {\n"
        "        'contract': 'aegis.playbook_sweep.v1',\n"
        "        'kind': 'strategy_axis',\n"
        "        'candidate_axis': [{'candidate_id': 'no-trades', 'params': {}}],\n"
        "        'materialize_signals': materialize_signals,\n"
        "    }\n"
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
        "result_schema": "playbook_sweep_result.v1",
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

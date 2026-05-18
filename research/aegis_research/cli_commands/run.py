from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.cli_support.errors import (
    ConfigCliError,
    ExecutionFailureError,
    InterruptedCliError,
)
from research.aegis_research.cli_support.output import (
    CommandResult,
    run_success_payload,
    safe_path,
    write_success,
)
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.config import (
    ConfigSelectionEvidence,
    ConfigValidationError,
    ExperimentConfig,
    ModelConfig,
    ResolvedExperimentConfig,
    ResolvedLaneConfig,
    known_config_secret_values,
    load_lane_config,
    redact_text,
    resolve_experiment_config,
)
from research.aegis_research.model_plugins import make_default_model_registry
from research.aegis_research.model_registry import freeze_model_registry
from research.aegis_research.playbook_registry import (
    PlaybookRegistryError,
    PlaybookSelection,
    discover_playbook_registry,
)
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.strategy_runs import run_strategy_sweep
from research.aegis_research.training import run_training


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run", help="Run a config")
    parser.add_argument("config", nargs="?", help="Path to run YAML")
    parser.add_argument(
        "-t",
        "--train",
        action="store_true",
        help="Run the config's train section for ML training",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    parser.add_argument(
        "--rerun-mode",
        choices=[RerunMode.NEW, RerunMode.DUPLICATE, RerunMode.FORK, RerunMode.OVERWRITE],
        default=RerunMode.NEW,
        help="Explicit run creation mode",
    )
    parser.add_argument("--run-id", help="Optional physical run id")
    parser.add_argument("--parent-run-id", help="Parent run id for forked runs")
    parser.add_argument("--supersedes-run-id", help="Prior run id superseded by overwrite mode")
    parser.set_defaults(handler=handle_run, command_name="run")


def handle_run(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    if args.config is None:
        if args.train:
            raise ConfigCliError("aerd run --train requires an explicit config")
        raise ConfigCliError("aerd run requires an explicit config; use --train for ML training")
    config_path = Path(args.config)

    if args.train:
        return _handle_train_run(args, config_path=config_path, json_mode=json_mode, **streams)

    return _handle_strategy_run(args, config_path=config_path, json_mode=json_mode, **streams)


def _handle_strategy_run(
    args: argparse.Namespace,
    *,
    config_path: Path,
    json_mode: bool,
    **streams: Any,
) -> int:

    run_refs: dict[str, Any] = {}
    try:
        if _looks_like_model_training_config(config_path):
            raise ConfigCliError(
                "model training configs are not accepted by default aerd run; use aerd run --train with a train section"
            )
        component_registry = discover_component_registry()
        playbook_registry = discover_playbook_registry(component_registry=component_registry)
        resolved = load_lane_config(
            config_path,
            component_registry=component_registry,
            expected_lane="run",
        )
        _validate_run_playbook_refs(resolved.config, playbook_registry)
    except (ConfigValidationError, PlaybookRegistryError) as error:
        raise ConfigCliError(str(error)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigCliError(str(error)) from error

    try:
        result = run_strategy_sweep(
            resolved,
            component_registry=component_registry,
            playbook_registry=playbook_registry,
            rerun_mode=args.rerun_mode,
            run_id=args.run_id,
            parent_run_id=args.parent_run_id,
            supersedes_run_id=args.supersedes_run_id,
            on_run_started=run_refs.update,
        )
        run_refs.update(result)
    except KeyboardInterrupt as error:
        raise InterruptedCliError(
            "strategy run interrupted",
            run_refs=_refreshed_run_refs(run_refs),
        ) from error
    except Exception as error:
        raise ExecutionFailureError(redact_text(str(error)), run_refs=_refreshed_run_refs(run_refs)) from error

    return write_success(
        CommandResult(
            command="run",
            payload=_run_payload(result, selection={"source": "explicit", "config_path": safe_path(config_path)}),
            human_lines=_human_run_lines(result),
        ),
        json_mode=json_mode,
        **streams,
    )


def _handle_train_run(
    args: argparse.Namespace,
    *,
    config_path: Path,
    json_mode: bool,
    **streams: Any,
) -> int:
    selection = {"source": "explicit", "config_path": safe_path(config_path) or str(config_path)}
    run_refs: dict[str, Any] = {}
    try:
        component_registry = discover_component_registry()
        model_registry = freeze_model_registry(make_default_model_registry())
        resolved = load_lane_config(
            config_path,
            component_registry=component_registry,
            expected_lane="train",
        )
        training_config = _training_experiment_config(
            resolved,
            selection=selection,
            model_registry=model_registry,
        )
        label_result_builder = _label_result_builder(resolved, component_registry)
    except (ConfigValidationError, ComponentRegistryError) as error:
        raise ConfigCliError(str(error)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigCliError(str(error)) from error

    known_secrets = known_config_secret_values(resolved.authored_config)
    try:
        result = run_training(
            training_config,
            label_result_builder=label_result_builder,
            rerun_mode=args.rerun_mode,
            run_id=args.run_id,
            parent_run_id=args.parent_run_id,
            supersedes_run_id=args.supersedes_run_id,
            on_run_started=run_refs.update,
        )
    except KeyboardInterrupt as error:
        raise InterruptedCliError(
            "training run interrupted",
            run_refs=_refreshed_run_refs(run_refs),
        ) from error
    except Exception as error:
        raise ExecutionFailureError(
            redact_text(str(error), known_secrets),
            run_refs=_refreshed_run_refs(run_refs),
        ) from error

    payload = run_success_payload(result, selection=selection)
    payload["mode"] = "train"
    payload["lane"] = "train"
    payload["evidence_type"] = "ml_training"
    return write_success(
        CommandResult(
            command="run",
            payload=payload,
            human_lines=_human_train_lines(result),
        ),
        json_mode=json_mode,
        **streams,
    )


def _looks_like_model_training_config(path: Path) -> bool:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        return False
    if "model" in raw or "labels" in raw or "split" in raw:
        return True
    return "train" in raw and not {"strategy", "indicator_refs", "ranking"}.intersection(raw)


def _training_experiment_config(
    resolved: ResolvedLaneConfig,
    *,
    selection: dict[str, Any],
    model_registry: Any,
) -> ResolvedExperimentConfig:
    config = resolved.config
    if config.lane != "train":
        raise ConfigCliError("aerd run --train requires a train-mode config")
    experiment_config = ExperimentConfig(
        name=config.name,
        schema_version=config.schema_version,
        data=config.data,
        indicators=config.indicators,
        split=config.split,
        model=ModelConfig(
            plugin_id=config.model.id,
            min_train_samples=config.model.min_train_samples,
            params=config.model.params,
        ),
        signals=config.signals,
        portfolio=config.portfolio,
        report=config.report,
        output_dir=config.output_dir,
    )
    resolve_experiment_config(experiment_config, model_registry=model_registry)
    return ResolvedExperimentConfig(
        config=experiment_config,
        raw_config_hash=resolved.raw_config_hash,
        authored_config=resolved.authored_config,
        source_path=resolved.source_path,
        model_registry=model_registry,
        selection=ConfigSelectionEvidence(
            source="explicit",
            config_path=selection["config_path"],
        ),
    )


def _label_result_builder(
    resolved: ResolvedLaneConfig,
    component_registry: FrozenComponentRegistry,
) -> Any:
    config = resolved.config
    definition = component_registry.get(ComponentSelection("labels", config.label.id))
    label_callable = definition.load_callable()
    params = dict(config.label.params)

    def build(close: Any, **_kwargs: Any) -> Any:
        result = label_callable(close, params=params)
        metadata = dict(getattr(result, "metadata", {}))
        metadata["source"] = {"kind": "component", "id": config.label.id}
        return replace(result, metadata=metadata)

    return build


def _validate_run_playbook_refs(config: Any, playbook_registry: Any) -> None:
    if config.strategy.source == "playbook":
        definition = playbook_registry.get(PlaybookSelection("strategies", config.strategy.id))
        _require_playbook_stage(definition.manifest.stages, "strategies", config.strategy.id)
    for ref in config.indicator_refs:
        if ref.source != "playbook":
            continue
        definition = playbook_registry.get(PlaybookSelection("indicators", ref.id))
        _require_playbook_stage(definition.manifest.stages, "indicators", ref.id)


def _require_playbook_stage(stages: tuple[str, ...], stage: str, playbook_id: str) -> None:
    if stage not in stages:
        raise PlaybookRegistryError(f"playbook {playbook_id!r} does not support {stage} runs")


def _run_payload(result: dict[str, Any], *, selection: dict[str, Any]) -> dict[str, Any]:
    leaderboard = result.get("leaderboard", {})
    return {
        "lane": "run",
        "mode": "strategy",
        "evidence_type": "strategy_sweep",
        "selection": selection,
        "run": {
            "id": result.get("run_id"),
            "status": result.get("status"),
            "run_dir": safe_path(result.get("run_dir")),
            "manifest_path": safe_path(result.get("manifest_path")),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
        },
        "artifacts": {"strategy_artifact_id": result.get("strategy_artifact_id")},
        "leaderboard": {
            "summary": leaderboard.get("summary"),
            "top_rows": leaderboard.get("rows", [])[:10],
        },
    }


def _human_run_lines(result: dict[str, Any]) -> tuple[str, ...]:
    return (
        f"Run: {safe_path(result.get('run_dir'))}",
        "Mode: strategy",
        "Evidence: strategy_sweep",
        f"Status: {result.get('status')}",
    )


def _human_train_lines(result: dict[str, Any]) -> tuple[str, ...]:
    report = result.get("report", {})
    lines = [
        f"Run: {safe_path(result.get('run_dir'))}",
        "Mode: train",
        "Evidence: ml_training",
        f"Status: {result.get('status')}",
    ]
    if isinstance(report, dict):
        lines.append(f"Verdict: {report.get('status')}")
    return tuple(lines)


def _refreshed_run_refs(run_refs: dict[str, Any]) -> dict[str, Any]:
    if not run_refs:
        return {}
    refs = dict(run_refs)
    manifest_path = refs.get("manifest_path")
    if not manifest_path:
        return refs
    try:
        payload = json.loads(Path(str(manifest_path)).read_text())
    except (OSError, json.JSONDecodeError):
        return refs
    run = payload.get("run", {})
    if isinstance(run, dict):
        refs["status"] = run.get("status", refs.get("status"))
        refs["finished_at"] = run.get("finished_at", refs.get("finished_at"))
    return refs

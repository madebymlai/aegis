from __future__ import annotations

import argparse
import json
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
from research.aegis_research.config import (
    ConfigSelectionEvidence,
    ConfigValidationError,
    known_config_secret_values,
    load_experiment_config,
    load_lane_config,
    redact_text,
    with_config_selection,
)
from research.aegis_research.model_plugins import make_default_model_registry
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.training import run_training


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("train", help="Run an ML training config")
    parser.add_argument("config", help="Path to training YAML")
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
    parser.set_defaults(handler=handle_train, command_name="train")


def handle_train(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    registry = make_default_model_registry()
    selection = {"source": "explicit", "config_path": safe_path(Path(args.config)) or str(args.config)}
    run_refs: dict[str, Any] = {}

    try:
        if _is_lane_train_config(Path(args.config)):
            load_lane_config(args.config, expected_lane="train")
            raise ConfigCliError(
                "train lane source refs are validated, but component-backed training execution is not enabled yet"
            )
        resolved = load_experiment_config(args.config, model_registry=registry)
        resolved = with_config_selection(
            resolved,
            ConfigSelectionEvidence(
                source="explicit",
                config_path=selection["config_path"],
            ),
            source_path=selection["config_path"],
        )
    except ConfigCliError:
        raise
    except ConfigValidationError as error:
        raise ConfigCliError(str(error)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigCliError(str(error)) from error

    known_secrets = known_config_secret_values(resolved.authored_config)
    try:
        result = run_training(
            resolved,
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
    payload["lane"] = "train"
    payload["evidence_type"] = "ml_training"
    return write_success(
        CommandResult(
            command="train",
            payload=payload,
            human_lines=_human_train_lines(result),
        ),
        json_mode=json_mode,
        **streams,
    )


def _is_lane_train_config(path: Path) -> bool:
    raw = yaml.safe_load(path.read_text())
    return isinstance(raw, dict) and raw.get("lane") == "train"


def _human_train_lines(result: dict[str, Any]) -> tuple[str, ...]:
    report = result.get("report", {})
    lines = [
        f"Train: {safe_path(result.get('run_dir'))}",
        "Lane: train",
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

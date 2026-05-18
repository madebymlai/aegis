from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.cli_support.defaults import DefaultSelection, resolve_default
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
    redact_text,
    with_config_selection,
)
from research.aegis_research.experiments import run_experiment
from research.aegis_research.model_plugins import make_default_model_registry
from research.aegis_research.provenance.recorder import RerunMode


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run", help="Run an experiment config")
    parser.add_argument("config", nargs="?", help="Path to experiment YAML")
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
    registry = make_default_model_registry()
    selection = _select_config(args.config)
    run_refs: dict[str, Any] = {}

    try:
        resolved = load_experiment_config(selection.config_path, model_registry=registry)
        resolved = with_config_selection(
            resolved,
            ConfigSelectionEvidence(
                source=selection.source,
                config_path=selection.display_path,
            ),
            source_path=selection.display_path,
        )
    except ConfigValidationError as error:
        raise ConfigCliError(str(error)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigCliError(str(error)) from error

    known_secrets = known_config_secret_values(resolved.authored_config)
    try:
        result = run_experiment(
            resolved,
            rerun_mode=args.rerun_mode,
            run_id=args.run_id,
            parent_run_id=args.parent_run_id,
            supersedes_run_id=args.supersedes_run_id,
            on_run_started=run_refs.update,
        )
    except KeyboardInterrupt as error:
        raise InterruptedCliError(
            "experiment run interrupted",
            run_refs=_refreshed_run_refs(run_refs),
        ) from error
    except Exception as error:
        raise ExecutionFailureError(
            redact_text(str(error), known_secrets),
            run_refs=_refreshed_run_refs(run_refs),
        ) from error

    return write_success(
        CommandResult(
            command="run",
            payload=run_success_payload(result, selection=selection.summary()),
            human_lines=_human_run_lines(result),
        ),
        json_mode=json_mode,
        **streams,
    )


def _select_config(config: str | None) -> DefaultSelection:
    if config is None:
        return resolve_default()
    path = Path(config)
    return DefaultSelection(
        config_path=path,
        display_path=safe_path(path) or str(config),
        source="explicit",
    )


def _human_run_lines(result: dict[str, Any]) -> tuple[str, ...]:
    report = result.get("report", {})
    lines = [f"Run: {safe_path(result.get('run_dir'))}", f"Status: {result.get('status')}"]
    if isinstance(report, dict):
        lines.append(f"Verdict: {report.get('status')}")
        reasons = report.get("reasons", [])
        if reasons:
            lines.append("Reason:")
            lines.extend(f"- {reason}" for reason in reasons)
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

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.aegis_research.cli_support.errors import (
    ConfigCliError,
    ExecutionFailureError,
    InterruptedCliError,
)
from research.aegis_research.cli_support.output import (
    CommandResult,
    safe_path,
    write_success,
)
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    discover_component_registry,
)
from research.aegis_research.config import (
    ConfigSelectionEvidence,
    ConfigValidationError,
    known_config_secret_values,
    load_run_config,
    redact_text,
    with_run_config_selection,
)
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.run_pipeline import run_strategy_sweep


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run", help="Run a config")
    parser.add_argument("config", nargs="?", help="Path to run YAML")
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
        raise ConfigCliError("aerd run requires an explicit config")
    config_path = Path(args.config)
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
        component_registry = discover_component_registry()
        resolved = load_run_config(
            config_path,
            component_registry=component_registry,
        )
        resolved = with_run_config_selection(
            resolved,
            ConfigSelectionEvidence(source="explicit", config_path=safe_path(config_path)),
        )
    except (ConfigValidationError, ComponentRegistryError) as error:
        raise ConfigCliError(str(error)) from error
    except OSError as error:
        raise ConfigCliError(str(error)) from error

    known_secrets = known_config_secret_values(resolved.authored_config)
    try:
        result = run_strategy_sweep(
            resolved,
            component_registry=component_registry,
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
    except ConfigValidationError as error:
        raise ConfigCliError(
            redact_text(str(error), known_secrets),
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
            payload=_run_payload(
                result, selection={"source": "explicit", "config_path": safe_path(config_path)}
            ),
            human_lines=_human_run_lines(result),
        ),
        json_mode=json_mode,
        **streams,
    )


def _run_payload(result: dict[str, Any], *, selection: dict[str, Any]) -> dict[str, Any]:
    leaderboard = result.get("leaderboard", {})
    return {
        "selection": selection,
        "run": {
            "id": result.get("run_id"),
            "status": result.get("status"),
            "run_dir": safe_path(result.get("run_dir")),
            "manifest_path": safe_path(result.get("manifest_path")),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
        },
        "artifacts": {
            "strategy_artifact_id": result.get("strategy_artifact_id"),
            "strategy_artifact_path": safe_path(result.get("strategy_artifact_path")),
        },
        "candidate_store": {
            "path": safe_path(result.get("candidate_store_path")),
        },
        "locks": result.get("locks", []),
        "leaderboard": {
            "summary": leaderboard.get("summary"),
            "top_rows": leaderboard.get("rows", [])[:10],
        },
    }


def _human_run_lines(result: dict[str, Any]) -> tuple[str, ...]:
    return (
        f"Run: {safe_path(result.get('run_dir'))}",
        f"Status: {result.get('status')}",
    )


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

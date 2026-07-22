from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from research.aegis_research.cli_support.errors import (
    ConfigCliError,
    ExecutionFailureError,
    InterruptedCliError,
)
from research.aegis_research.cli_support.output import (
    CommandResult,
    real_path_text,
    run_refs,
    write_success,
)
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    discover_component_registry,
)
from research.aegis_research.configuration import (
    ConfigSelectionEvidence,
    ConfigValidationError,
    load_run_config,
    with_run_config_selection,
)
from research.aegis_research.run_pipeline import run_strategy_sweep


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run", help="Run a config")
    parser.add_argument("config", nargs="?", help="Path to run YAML")
    parser.add_argument("--run-id", help="Optional physical run id")
    parser.set_defaults(handler=handle_run, command_name="run")


def handle_run(args: argparse.Namespace, **streams: Any) -> int:
    if args.config is None:
        raise ConfigCliError("aerd run requires an explicit config")
    config_path = Path(args.config)
    return _handle_strategy_run(args, config_path=config_path, **streams)


def _handle_strategy_run(
    args: argparse.Namespace,
    *,
    config_path: Path,
    **streams: Any,
) -> int:
    failure_refs: dict[str, Any] = {}
    selection_evidence = ConfigSelectionEvidence(
        source="explicit", config_path=str(config_path.resolve())
    )
    try:
        component_registry = discover_component_registry()
        resolved = load_run_config(
            config_path,
            component_registry=component_registry,
        )
        resolved = with_run_config_selection(
            resolved,
            selection_evidence,
        )
    except (ConfigValidationError, ComponentRegistryError) as error:
        raise ConfigCliError(str(error)) from error
    except OSError as error:
        raise ConfigCliError(str(error)) from error

    try:
        result = run_strategy_sweep(
            resolved,
            component_registry=component_registry,
            run_id=args.run_id,
            on_run_refs=failure_refs.update,
        )
        failure_refs.update(result)
    except KeyboardInterrupt as error:
        raise InterruptedCliError(
            "strategy run interrupted",
            run_refs=failure_refs,
        ) from error
    except ConfigValidationError as error:
        raise ConfigCliError(
            str(error),
            run_refs=failure_refs,
        ) from error
    except Exception as error:
        raise ExecutionFailureError(
            str(error),
            run_refs=failure_refs,
        ) from error

    return write_success(
        CommandResult(
            command="run",
            payload=_run_payload(result, selection_evidence=selection_evidence),
        ),
        **streams,
    )


def _run_payload(
    result: dict[str, Any],
    *,
    selection_evidence: ConfigSelectionEvidence,
) -> dict[str, Any]:
    return {
        "selection": selection_evidence.manifest(),
        "run": run_refs(result),
        "artifacts": {
            "strategy_artifact_id": result["strategy_artifact_id"],
            "strategy_artifact_path": real_path_text(result["strategy_artifact_path"]),
        },
        "candidate_store": {
            "path": real_path_text(result["candidate_store_path"]),
        },
        "optimization": result["optimization"],
        "candidates": result["candidates"],
    }

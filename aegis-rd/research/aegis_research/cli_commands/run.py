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
    write_success,
)
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    discover_component_registry,
)
from research.aegis_research.configuration import (
    ConfigValidationError,
    load_run_config,
)
from research.aegis_research.run.identity import InvalidRunIdError, RunId
from research.aegis_research.run.pipeline import run_strategy_sweep
from research.aegis_research.run.result import RunResult


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
    explicit_run_id = _explicit_run_id(args.run_id)
    early_failure_refs = {"run_id": str(explicit_run_id)} if explicit_run_id is not None else None
    try:
        component_registry = discover_component_registry()
        resolved = load_run_config(
            config_path,
            component_registry=component_registry,
        )
    except (ConfigValidationError, ComponentRegistryError) as error:
        raise ConfigCliError(str(error), run_refs=early_failure_refs) from error
    except OSError as error:
        raise ConfigCliError(str(error), run_refs=early_failure_refs) from error

    attempted_run_id = explicit_run_id or RunId.create(None, run_name=resolved.config.name)
    failure_refs = {"run_id": str(attempted_run_id)}
    try:
        result = run_strategy_sweep(
            resolved,
            component_registry=component_registry,
            run_id=str(attempted_run_id),
        )
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
            payload=_run_payload(result),
        ),
        **streams,
    )


def _explicit_run_id(value: str | None) -> RunId | None:
    if value is None:
        return None
    try:
        return RunId(value)
    except InvalidRunIdError as error:
        raise ConfigCliError(str(error)) from error


def _run_payload(result: RunResult) -> dict[str, Any]:
    return {
        "run": {"id": str(result.run_id)},
        "candidate_store": {
            "path": real_path_text(result.candidate_store_path),
        },
        "optimization": result.optimization.to_dict(),
        "candidates": [candidate.to_dict() for candidate in result.candidates],
    }

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.cli_support.errors import ConfigCliError, ExecutionFailureError
from research.aegis_research.cli_support.output import CommandResult, safe_path, write_success
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import ConfigValidationError, load_lane_config
from research.aegis_research.play import run_play
from research.aegis_research.playbook_registry import (
    PlaybookRegistryError,
    discover_playbook_registry,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("play", help="Run a repo-controlled exploratory playbook")
    parser.add_argument("config", help="Path to play YAML")
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    parser.set_defaults(handler=handle_play, command_name="play")


def handle_play(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    try:
        component_registry = discover_component_registry()
        playbook_registry = discover_playbook_registry(component_registry=component_registry)
        resolved = load_lane_config(
            args.config,
            component_registry=component_registry,
            expected_lane="play",
        )
    except (ConfigValidationError, PlaybookRegistryError) as error:
        raise ConfigCliError(str(error)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigCliError(str(error)) from error

    try:
        result = run_play(resolved, playbook_registry=playbook_registry)
    except PlaybookRegistryError as error:
        raise ConfigCliError(str(error)) from error
    except Exception as error:
        raise ExecutionFailureError(str(error)) from error

    return write_success(
        CommandResult(
            command="play",
            payload={
                "lane": result["lane"],
                "evidence_type": result["evidence_type"],
                "selection": {"source": "explicit", "config_path": safe_path(Path(args.config))},
                "playbooks": result["playbooks"],
                "artifacts": result["artifacts"],
                "ranking": result["ranking"],
            },
            human_lines=(
                f"Play: {result['name']}",
                "Lane: play",
                f"Playbooks: {len(result['playbooks'])}",
                f"Artifact: {safe_path(result['artifacts']['last_run_dir'])}",
            ),
        ),
        json_mode=json_mode,
        **streams,
    )

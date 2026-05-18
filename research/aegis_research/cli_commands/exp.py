from __future__ import annotations

import argparse
from typing import Any

import yaml

from research.aegis_research.cli_support.defaults import set_default
from research.aegis_research.cli_support.errors import ConfigCliError
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.config import ConfigValidationError
from research.aegis_research.model_plugins import make_default_model_registry


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    exp_parser = subparsers.add_parser("exp", help="Manage experiment CLI state")
    exp_subparsers = exp_parser.add_subparsers(dest="exp_command", required=True)

    defaults_parser = exp_subparsers.add_parser("defaults", help="Manage local defaults")
    defaults_subparsers = defaults_parser.add_subparsers(
        dest="defaults_command",
        required=True,
    )

    set_parser = defaults_subparsers.add_parser("set", help="Set the local default experiment")
    set_parser.add_argument("config", help="Repo-local experiment YAML")
    set_parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    set_parser.set_defaults(handler=handle_defaults_set, command_name="exp defaults set")


def handle_defaults_set(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    registry = make_default_model_registry()
    try:
        selection = set_default(args.config, model_registry=registry)
    except ConfigValidationError as error:
        raise ConfigCliError(str(error)) from error
    except (OSError, yaml.YAMLError) as error:
        raise ConfigCliError(str(error)) from error

    return write_success(
        CommandResult(
            command="exp defaults set",
            payload={"selection": selection.summary()},
            human_lines=(f"Default experiment: {selection.display_path}",),
        ),
        json_mode=json_mode,
        **streams,
    )

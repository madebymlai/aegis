from __future__ import annotations

import argparse
from typing import Any

from research.aegis_research.cli_support.errors import ConfigCliError
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    discover_component_registry,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("components", help="Inspect discovered components")
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    parser.set_defaults(handler=handle_show_components, command_name="show")


def handle_show_components(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    try:
        payload = discover_component_registry().public_snapshot()
    except ComponentRegistryError as error:
        raise ConfigCliError(str(error)) from error
    return write_success(
        CommandResult(
            command="show",
            payload=payload,
            human_lines=_human_component_lines(payload),
        ),
        json_mode=json_mode,
        **streams,
    )


def _human_component_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    lines = [f"fingerprint: {payload['fingerprint']}"]
    for family, definitions in payload.get("families", {}).items():
        lines.append(f"{family}:")
        for component_id in definitions:
            lines.append(f"  - {component_id}")
    return tuple(lines)

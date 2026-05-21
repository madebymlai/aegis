from __future__ import annotations

import argparse
from typing import Any

from research.aegis_research.cli_support.errors import ConfigCliError
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.run_splits import (
    splitter_catalog_payload,
    splitter_method_info,
    splitter_method_names,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("splitters", help="Inspect VBT splitter methods")
    parser.add_argument("method", nargs="?", help="VBT Splitter method such as from_rolling")
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    parser.set_defaults(handler=handle_show_splitters, command_name="show")


def handle_show_splitters(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    method = args.method
    if not method:
        return _write_splitter_catalog(json_mode=json_mode, **streams)
    try:
        payload = splitter_method_info(method).payload()
    except ValueError as error:
        raise ConfigCliError(str(error)) from error

    return write_success(
        CommandResult(
            command="show",
            payload=payload,
            human_lines=_human_method_lines(payload),
        ),
        json_mode=json_mode,
        **streams,
    )


def _write_splitter_catalog(*, json_mode: bool, **streams: Any) -> int:
    payload = splitter_catalog_payload()
    return write_success(
        CommandResult(
            command="show",
            payload=payload,
            human_lines=splitter_method_names(),
        ),
        json_mode=json_mode,
        **streams,
    )


def _human_method_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    lines = [f"method: {payload['method']}"]
    lines.append(f"run_scoring_set_policy: {payload['run_scoring_set_policy']}")
    required = payload.get("required_params", [])
    if required:
        lines.append(f"required_params: {', '.join(required)}")
    denied = payload.get("denied_internal_params", [])
    if denied:
        lines.append(f"denied_internal_params: {', '.join(denied)}")
    lines.append("params:")
    for param in payload.get("params", []):
        suffix = "required" if param["required"] else f"default={param.get('default')!r}"
        if param.get("denied"):
            suffix = f"{suffix}, denied"
        lines.append(f"  - {param['name']}: {suffix}")
    return tuple(lines)

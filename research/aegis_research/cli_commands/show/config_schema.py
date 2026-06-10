"""``aerd show config-schema`` — Run Config forward-contract authoring guide.

Thin pass-through over ``configuration.config_schema_guide.render_config_schema_guide``.
The deep module is the configuration package (the contract owner), per ADR-0019.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, TextIO

from research.aegis_research.cli_support.output import (
    CLI_JSON_SCHEMA_VERSION,
    CommandResult,
    write_success,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "config-schema",
        help="Print the Run Config forward-contract authoring guide",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result wrapping the markdown",
    )
    parser.set_defaults(handler=handle_show_config_schema, command_name="show")


def handle_show_config_schema(args: argparse.Namespace, *, json_mode: bool, **streams: Any) -> int:
    from research.aegis_research.configuration.config_schema_guide import (
        render_config_schema_guide,
    )

    markdown = render_config_schema_guide()

    if json_mode:
        stdout: TextIO = streams.get("stdout") or sys.stdout
        return _write_json(markdown, stdout)

    return write_success(
        CommandResult(
            command="show",
            human_lines=(markdown,),
        ),
        json_mode=False,
        **streams,
    )


def _write_json(markdown: str, stdout: TextIO) -> int:
    """Write the guide as a JSON envelope, preserving full markdown content.

    Bypasses ``write_success`` / ``safe_json_value`` because the standard
    payload serialization clips strings to ``MAX_REASON_CHARS`` (500).
    """
    payload = {
        "schema_version": CLI_JSON_SCHEMA_VERSION,
        "command": "show",
        "status": "success",
        "ok": True,
        "format": "markdown",
        "content": markdown,
    }
    stdout.write(json.dumps(payload, allow_nan=False, sort_keys=True) + "\n")
    return 0

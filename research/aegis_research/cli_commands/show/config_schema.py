"""``aerd show config-schema`` — Run Config forward-contract authoring guide.

Thin pass-through over ``configuration.config_schema_guide.render_config_schema_guide``.
The deep module is the configuration package (the contract owner), per ADR-0019.
"""

from __future__ import annotations

import argparse
from typing import Any

from research.aegis_research.cli_support.output import write_markdown_guide


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "config-schema",
        help="Print the Run Config forward-contract authoring guide",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a structured JSON result wrapping the markdown",
    )
    parser.set_defaults(handler=handle_show_config_schema, command_name="show")


def handle_show_config_schema(args: argparse.Namespace, **streams: Any) -> int:
    json_mode = args.json
    from research.aegis_research.configuration.config_schema_guide import (
        GUIDE_SCHEMA_VERSION,
        render_config_schema_guide,
    )

    return write_markdown_guide(
        render_config_schema_guide(),
        command="show",
        schema_version=GUIDE_SCHEMA_VERSION,
        json_mode=json_mode,
        **streams,
    )

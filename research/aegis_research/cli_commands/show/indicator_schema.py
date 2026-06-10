"""``aerd show indicator-schema`` — Indicator component authoring guide.

Thin pass-through over ``render_indicator_schema_guide()`` in the
component-registry package (ADR-0019: the deep module is the contract
owner, not the CLI).
"""

from __future__ import annotations

import argparse
from typing import Any

from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.component_registry.indicator_guide import (
    _GUIDE_SCHEMA_VERSION,
    render_indicator_schema_guide,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "indicator-schema",
        help="Show the Indicator Component authoring guide",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    parser.set_defaults(handler=handle_show_indicator_schema, command_name="show")


def handle_show_indicator_schema(
    args: argparse.Namespace,
    *,
    json_mode: bool,
    **streams: Any,
) -> int:
    markdown = render_indicator_schema_guide()
    return write_success(
        CommandResult(
            command="show",
            payload={
                "format": "markdown",
                "schema_version": _GUIDE_SCHEMA_VERSION,
                "content": markdown,
            },
            human_lines=(markdown.rstrip("\n"),),
        ),
        json_mode=json_mode,
        **streams,
    )

"""``aerd show indicator-schema`` — Indicator component authoring guide.

Thin pass-through over ``render_indicator_schema_guide()`` in the
component-registry package (ADR-0019: the deep module is the contract
owner, not the CLI).
"""

from __future__ import annotations

import argparse
from typing import Any

from research.aegis_research.cli_support.output import write_markdown_guide


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "indicator-schema",
        help="Show the Indicator Component authoring guide",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a structured JSON result",
    )
    parser.set_defaults(handler=handle_show_indicator_schema, command_name="show")


def handle_show_indicator_schema(
    args: argparse.Namespace,
    **streams: Any,
) -> int:
    json_mode = args.json
    from research.aegis_research.component_registry.authoring.indicator_guide import (
        GUIDE_SCHEMA_VERSION,
        render_indicator_schema_guide,
    )

    return write_markdown_guide(
        render_indicator_schema_guide(),
        command="show",
        schema_version=GUIDE_SCHEMA_VERSION,
        json_mode=json_mode,
        **streams,
    )

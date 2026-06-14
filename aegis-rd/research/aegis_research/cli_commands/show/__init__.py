from __future__ import annotations

import argparse

from research.aegis_research.cli_commands.show import (
    components,
    config_schema,
    indicator_schema,
    splitters,
    strategy_schema,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("show", help="Inspect discoverable Aegis catalogs")
    show_subparsers = parser.add_subparsers(dest="show_module", required=True)
    components.register(show_subparsers)
    config_schema.register(show_subparsers)
    indicator_schema.register(show_subparsers)
    splitters.register(show_subparsers)
    strategy_schema.register(show_subparsers)

from __future__ import annotations

import argparse

from research.aegis_research.cli_commands.show import splitters


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("show", help="Inspect discoverable Aegis catalogs")
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit a structured JSON result",
    )
    show_subparsers = parser.add_subparsers(dest="show_module", required=True)
    splitters.register(show_subparsers)

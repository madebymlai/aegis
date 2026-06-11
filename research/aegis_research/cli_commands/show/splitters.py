from __future__ import annotations

import argparse
from typing import Any

from research.aegis_research.cli_support.errors import ConfigCliError
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.run_splits import (
    splitter_catalog_payload,
    splitter_method_info,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("splitters", help="Inspect VBT splitter methods")
    parser.add_argument("method", nargs="?", help="VBT Splitter method such as from_rolling")
    parser.set_defaults(handler=handle_show_splitters, command_name="show")


def handle_show_splitters(args: argparse.Namespace, **streams: Any) -> int:
    method = args.method
    if method:
        try:
            payload = splitter_method_info(method).payload()
        except ValueError as error:
            raise ConfigCliError(str(error)) from error
    else:
        payload = splitter_catalog_payload()
    return write_success(CommandResult(command="show", payload=payload), **streams)

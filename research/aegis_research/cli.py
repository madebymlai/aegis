from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn, TextIO

from research.aegis_research.cli_commands import run, show
from research.aegis_research.cli_support.errors import (
    CliError,
    InternalCliError,
    InterruptedCliError,
    InvocationError,
    ParserExit,
)
from research.aegis_research.cli_support.output import json_requested, write_error


class AerdArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InvocationError(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message, sys.stderr)
        raise ParserExit(status, message)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return _main(args, stdout=sys.stdout, stderr=sys.stderr)


def _main(argv: Sequence[str], *, stdout: TextIO, stderr: TextIO) -> int:
    json_mode = json_requested(argv)
    command_name: str | None = None
    try:
        parser = build_parser()
        parsed = parser.parse_args(list(argv))
        command_name = getattr(parsed, "command_name", None)
        handler = getattr(parsed, "handler", None)
        if handler is None:
            return write_error(
                InvocationError("missing command"),
                command=command_name,
                json_mode=json_mode,
                stderr=stderr,
            )
        return handler(parsed, json_mode=json_mode, stdout=stdout, stderr=stderr)
    except ParserExit as exit_error:
        return exit_error.status
    except KeyboardInterrupt:
        return write_error(
            InterruptedCliError("command interrupted"),
            command=command_name,
            json_mode=json_mode,
            stderr=stderr,
        )
    except CliError as error:
        return write_error(error, command=command_name, json_mode=json_mode, stderr=stderr)
    except Exception as error:
        return write_error(
            InternalCliError(str(error)),
            command=command_name,
            json_mode=json_mode,
            stderr=stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = AerdArgumentParser(prog="aerd")
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit structured JSON where supported",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run.register(subparsers)
    show.register(subparsers)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from research.aegis_research.cli_support.errors import (
    CliError,
    ConfigCliError,
    ExecutionFailureError,
)
from research.aegis_research.cli_support.output import CommandResult, write_success
from research.aegis_research.configuration import ConfigValidationError
from research.aegis_research.execution_bundle import (
    FigiResolver,
    UnlockedBundleConfigError,
    assemble_bundle,
)
from research.aegis_research.execution_bundle_wheel import write_wheel
from research.aegis_research.market_data.figi import resolve_symbol_figis


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("export", help="Export a locked config as an execution bundle")
    parser.add_argument("--config", required=True, help="Path to locked run YAML")
    parser.add_argument("--out", help="Output directory for the wheel")
    parser.set_defaults(handler=handle_export, command_name="export")


def handle_export(args: argparse.Namespace, **streams: Any) -> int:
    try:
        out_dir = _default_bundle_dir() if args.out is None else Path(args.out)
        wheel_path = export_locked_bundle(Path(args.config), out_dir=out_dir)
    except ConfigValidationError as error:
        raise ConfigCliError(str(error)) from error
    except UnlockedBundleConfigError as error:
        raise ConfigCliError(str(error)) from error
    except CliError:
        raise
    except Exception as error:
        raise ExecutionFailureError(str(error)) from error
    return write_success(
        CommandResult(
            command="export",
            payload={
                "wheel": str(wheel_path),
                "install": f"uv add {wheel_path}",
            },
        ),
        **streams,
    )


def export_locked_bundle(
    config_path: Path, *, out_dir: Path, figi_resolver: FigiResolver | None = None
) -> Path:
    resolver = resolve_symbol_figis if figi_resolver is None else figi_resolver
    artifact = assemble_bundle(config_path, figi_resolver=resolver)
    return write_wheel(artifact, out_dir)


def _default_bundle_dir() -> Path:
    cwd = Path.cwd().resolve(strict=False)
    for parent in (cwd, *cwd.parents):
        if (parent / "CONTEXT-MAP.md").exists() and (parent / "aegis-rd").exists():
            return parent / "bundles"
    return cwd / "bundles"

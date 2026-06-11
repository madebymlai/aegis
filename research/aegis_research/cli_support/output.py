from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from research.aegis_research.cli_support.errors import (
    CliError,
    ErrorCategory,
    InternalCliError,
    exit_code_for,
)
from research.aegis_research.configuration import to_builtin

CLI_JSON_SCHEMA_VERSION = 1
MAX_ERROR_MESSAGE_CHARS = 1000
MAX_REASON_CHARS = 500
MAX_REASON_COUNT = 10


@dataclass(frozen=True)
class CommandResult:
    command: str
    payload: Mapping[str, Any] = field(default_factory=dict)


def write_success(
    result: CommandResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Emit the JSON success envelope on stdout — the CLI's one success
    contract (ADR-0021). Commands with a human success mode render it
    themselves via ``write_human_lines``."""
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    payload = _envelope(result.command, "success", result.payload)
    document = _json_document(payload)
    if document is None:
        return write_error(
            InternalCliError("CLI result could not be serialized as JSON"),
            command=result.command,
            stderr=stderr,
        )
    stdout.write(document)
    return 0


def write_human_lines(
    lines: tuple[str, ...],
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stdout.write("\n".join(lines) + "\n")
    return 0


def write_markdown_guide(
    markdown: str,
    *,
    command: str,
    schema_version: str,
    json_mode: bool,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Emit a rendered markdown guide for an ``aerd show *-schema`` command.

    Human mode prints the markdown; ``--json`` wraps it in the standard
    envelope as ``{"format": "markdown", "content": ...}``. Unlike
    ``write_success``, the ``content`` is not passed through ``safe_json_value``
    (which clips every string to ``MAX_REASON_CHARS``), so the full guide
    survives JSON serialization.
    """
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if json_mode:
        payload = {
            **_envelope_header(command, "success", schema_version=schema_version),
            "format": "markdown",
            "content": markdown,
        }
        document = _json_document(payload)
        if document is None:
            return write_error(
                InternalCliError("CLI guide could not be serialized as JSON"),
                command=command,
                stderr=stderr,
            )
        stdout.write(document)
        return 0

    stdout.write(markdown.rstrip("\n") + "\n")
    return 0


def write_error(
    error: CliError,
    *,
    command: str | None,
    stderr: TextIO | None = None,
) -> int:
    """Emit the JSON error envelope unconditionally on stderr for every command."""
    stderr = stderr or sys.stderr
    exit_code = exit_code_for(error)
    payload = _envelope(
        command or "unknown",
        "error",
        {
            "error": {
                "category": error.category,
                "message": clip_message(error.message),
                "details": safe_json_value(error.details),
            }
        },
    )
    if error.run_refs:
        payload["run"] = run_refs(error.run_refs)
    document = _json_document(payload)
    if document is None:
        fallback_message = "CLI error could not be serialized as JSON"
        fallback = {
            **_envelope_header(command or "unknown", "error"),
            "error": {
                "category": ErrorCategory.INTERNAL,
                "message": fallback_message,
                "details": {},
            },
        }
        document = json.dumps(fallback, allow_nan=False, sort_keys=True) + "\n"
        exit_code = exit_code_for(InternalCliError(fallback_message))
    stderr.write(document)
    return exit_code



def run_refs(refs: Mapping[str, Any]) -> dict[str, Any]:
    """Project a run-identity block with real, resolved absolute paths — no
    path scrubbing (ADR-0021).

    Consumed by both the success payload and the error envelope so the
    two run blocks cannot drift.
    """
    return {
        "id": refs.get("run_id") or refs.get("id"),
        "status": refs.get("status"),
        "run_dir": real_path_text(refs.get("run_dir")),
        "manifest_path": real_path_text(refs.get("manifest_path")),
        "started_at": refs.get("started_at"),
        "finished_at": refs.get("finished_at"),
    }


def real_path_text(value: Any) -> str | None:
    """The CLI's one path shape: a real, resolved absolute path as text
    (ADR-0021)."""
    if value is None:
        return None
    return str(Path(value).resolve(strict=False))


def clip_message(text: str, *, max_chars: int = MAX_ERROR_MESSAGE_CHARS) -> str:
    return str(text)[:max_chars]


def safe_json_value(value: Any) -> Any:
    value = to_builtin(value)
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return clip_message(value, max_chars=MAX_REASON_CHARS)
    if isinstance(value, Path):
        return real_path_text(value)
    if isinstance(value, Mapping):
        return {str(key): safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [safe_json_value(item) for item in value]
    return clip_message(repr(value), max_chars=MAX_REASON_CHARS)


def _envelope_header(
    command: str,
    status: str,
    *,
    schema_version: Any = CLI_JSON_SCHEMA_VERSION,
) -> dict[str, Any]:
    """The one home of the CLI JSON envelope shape.

    Guides carry their own ``schema_version`` in the envelope slot; every
    other command uses ``CLI_JSON_SCHEMA_VERSION``.
    """
    return {
        "schema_version": schema_version,
        "command": command,
        "status": status,
        "ok": status == "success",
    }


def _envelope(command: str, status: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_envelope_header(command, status),
        **safe_json_value(payload),
    }


def _json_document(payload: Mapping[str, Any]) -> str | None:
    try:
        return json.dumps(payload, allow_nan=False, sort_keys=True) + "\n"
    except (TypeError, ValueError):
        return None

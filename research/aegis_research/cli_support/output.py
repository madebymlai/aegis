from __future__ import annotations

import json
import math
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from research.aegis_research.cli_support.errors import (
    CliError,
    ErrorCategory,
    InternalCliError,
    exit_code_for,
)
from research.aegis_research.config import redact_text, to_builtin

CLI_JSON_SCHEMA_VERSION = 1
MAX_ERROR_MESSAGE_CHARS = 1000
MAX_REASON_CHARS = 500
MAX_REASON_COUNT = 10


@dataclass(frozen=True)
class CommandResult:
    command: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    human_lines: tuple[str, ...] = ()


def json_requested(argv: Sequence[str]) -> bool:
    return "--json" in argv


def write_success(
    result: CommandResult,
    *,
    json_mode: bool,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if json_mode:
        payload = _envelope(result.command, "success", result.payload)
        document = _json_document(payload)
        if document is None:
            return write_error(
                InternalCliError("CLI result could not be serialized as JSON"),
                command=result.command,
                json_mode=True,
                stderr=stderr,
            )
        stdout.write(document)
        return 0

    lines = result.human_lines or ("OK",)
    stdout.write("\n".join(lines) + "\n")
    return 0


def write_error(
    error: CliError,
    *,
    command: str | None,
    json_mode: bool,
    stderr: TextIO | None = None,
) -> int:
    stderr = stderr or sys.stderr
    exit_code = exit_code_for(error)
    if json_mode:
        payload = _envelope(
            command or "unknown",
            "error",
            {
                "error": {
                    "category": error.category,
                    "message": safe_message(error.message),
                    "details": safe_json_value(error.details),
                }
            },
        )
        if error.run_refs:
            payload["run"] = safe_run_refs(error.run_refs)
        document = _json_document(payload)
        if document is None:
            fallback = {
                "schema_version": CLI_JSON_SCHEMA_VERSION,
                "command": command or "unknown",
                "status": "error",
                "ok": False,
                "error": {
                    "category": ErrorCategory.INTERNAL,
                    "message": "CLI error could not be serialized as JSON",
                    "details": {},
                },
            }
            document = json.dumps(fallback, allow_nan=False, sort_keys=True) + "\n"
            exit_code = exit_code_for(InternalCliError(fallback["error"]["message"]))
        stderr.write(document)
        return exit_code

    stderr.write(f"{error.category}: {safe_message(error.message)}\n")
    return exit_code


def run_success_payload(
    result: Mapping[str, Any],
    *,
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    report = result.get("report")
    return {
        "selection": safe_json_value(selection),
        "run": safe_run_refs(result),
        "report": report_summary(report) if isinstance(report, Mapping) else None,
        "artifacts": {
            "manifest_path": safe_path(result.get("manifest_path")),
            "report_artifact_id": result.get("report_artifact_id"),
        },
    }


def report_summary(report: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    reasons = [
        safe_message(str(reason), max_chars=MAX_REASON_CHARS)
        for reason in report.get("reasons", [])
    ]
    gate_outcomes = report.get("gate_outcomes", [])
    return {
        "status": report.get("status"),
        "reasons": reasons[:MAX_REASON_COUNT],
        "reason_count": len(reasons),
        "gate_count": len(gate_outcomes) if isinstance(gate_outcomes, list) else None,
    }


def safe_run_refs(refs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": refs.get("run_id") or refs.get("id"),
        "status": refs.get("status"),
        "run_dir": safe_path(refs.get("run_dir")),
        "manifest_path": safe_path(refs.get("manifest_path")),
        "started_at": refs.get("started_at"),
        "finished_at": refs.get("finished_at"),
    }


def safe_path(value: Any) -> str | None:
    if value is None:
        return None
    path_text = str(value)
    path = Path(path_text)
    was_relative = not path.is_absolute()
    resolved = (
        (Path.cwd() / path).resolve(strict=False) if was_relative else path.resolve(strict=False)
    )
    cwd = Path.cwd().resolve(strict=False)
    try:
        return resolved.relative_to(cwd).as_posix()
    except ValueError:
        if was_relative:
            return "<path>"

    for base in (Path.home(), Path(tempfile.gettempdir())):
        try:
            relative = resolved.relative_to(base.resolve(strict=False))
        except ValueError:
            continue
        prefix = "~" if base == Path.home() else "<tmp>"
        return str(Path(prefix) / relative).replace("\\", "/")
    return "<path>"


def safe_message(text: str, *, max_chars: int = MAX_ERROR_MESSAGE_CHARS) -> str:
    message = redact_text(str(text))
    message = message.replace(str(Path.home()), "~")
    message = message.replace(tempfile.gettempdir(), "<tmp>")
    message = re.sub(r"(?<!\w)/(?:[^\s'\"]+/)*[^\s'\"]+", "<path>", message)
    return message[:max_chars]


def safe_json_value(value: Any) -> Any:
    value = to_builtin(value)
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return safe_message(value, max_chars=MAX_REASON_CHARS)
    if isinstance(value, Path):
        return safe_path(value)
    if isinstance(value, Mapping):
        return {str(key): safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [safe_json_value(item) for item in value]
    return safe_message(repr(value), max_chars=MAX_REASON_CHARS)


def _envelope(command: str, status: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CLI_JSON_SCHEMA_VERSION,
        "command": command,
        "status": status,
        "ok": status == "success",
        **safe_json_value(payload),
    }


def _json_document(payload: Mapping[str, Any]) -> str | None:
    try:
        return json.dumps(payload, allow_nan=False, sort_keys=True) + "\n"
    except (TypeError, ValueError):
        return None

from __future__ import annotations

import json
import math
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
from research.aegis_research.configuration import DEFAULT_LOCK_ROLE, to_builtin

CLI_JSON_SCHEMA_VERSION = 1
MAX_ERROR_MESSAGE_CHARS = 1000
MAX_REASON_CHARS = 500
MAX_REASON_COUNT = 10


@dataclass(frozen=True)
class CommandResult:
    command: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    human_lines: tuple[str, ...] = ()


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
                stderr=stderr,
            )
        stdout.write(document)
        return 0

    lines = result.human_lines or ("OK",)
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
        payload["run"] = safe_run_refs(error.run_refs)
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


def held_out_summary_lines(
    optimization: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Held-out-first candidate table for human run output.

    Leads with the held-out (out-of-sample) value of the ranking metric — the
    number to treat as the run's result — with the in-sample (selection-optimistic)
    value and the selection->held-out gap as secondary columns, plus a one-line
    warning when the best candidate collapses out-of-sample.
    """
    if not candidates:
        return ()
    metric = optimization.get("ranking_metric") or "ranking metric"
    lines = [
        f"Ranking metric: {metric} — held-out (out-of-sample) is the headline; "
        "in-sample is selection-optimistic",
        f"  {'role':<8}{'held-out':>12}{'in-sample':>12}{'gap':>12}",
    ]
    for candidate in candidates:
        headline = candidate.get("held_out_headline") or {}
        lines.append(
            f"  {candidate.get('role', '')!s:<8}"
            f"{_metric_cell(headline.get('held_out')):>12}"
            f"{_metric_cell(headline.get('selection')):>12}"
            f"{_metric_cell(headline.get('gap')):>12}"
        )
    warning = optimization.get("held_out_warning")
    if warning:
        lines.append(f"WARNING: {warning}")
    non_exec_line = _non_executable_rows_line(optimization)
    if non_exec_line:
        lines.append(non_exec_line)
    lines.append(_researched_ratio_line(optimization))
    return tuple(lines)


def reproduce_lock_lines(
    run_id: str | None,
    candidates: Sequence[Mapping[str, Any]],
    *,
    store_path: str | None,
) -> tuple[str, ...]:
    """Copy-paste ``lock:`` handles for reproducing each representative candidate.

    Each representative role yields the exact scalar a user pastes into a Run Config's
    ``lock:`` — best is the default role (a bare ``run_id``), the others carry ``:role``.
    The footer names the run_id and the candidate-store path so the handle is
    discoverable straight from the terminal — no ``--json`` or raw SQL required.
    """
    if not run_id or not candidates:
        return ()
    lines = ["Reproduce a representative candidate — paste a lock: line into a Run Config:"]
    for candidate in candidates:
        role = str(candidate.get("role", ""))
        handle = run_id if role == DEFAULT_LOCK_ROLE else f"{run_id}:{role}"
        lines.append(f"  {role:<8}lock: {handle}")
    lines.append(f"run_id: {run_id}")
    if store_path:
        lines.append(f"candidate store: {store_path}")
    return tuple(lines)


_PURGED_METHOD_SUBSTRINGS = ("purged", "embargo")


def _non_executable_rows_line(optimization: Mapping[str, Any]) -> str | None:
    """Report line for non-executable rebalance rows, or None.

    Renders only when non_executable_rows is non-zero. Under a
    purged/embargoed split method the line is neutral (the count is
    expected); under a contiguous split method it is WARNING-prefixed
    (the count should have been zero — upstream invariant breach).
    """
    count = optimization.get("non_executable_rows", 0)
    if not count:
        return None
    split_method = str(optimization.get("split_method", ""))
    is_purged = any(marker in split_method for marker in _PURGED_METHOD_SUBSTRINGS)
    if is_purged:
        return f"non-executable rebalance rows: {count} (held at split seams)"
    return f"WARNING: non-executable rebalance rows: {count} (should be zero — invariant breach)"


def _researched_ratio_line(optimization: Mapping[str, Any]) -> str:
    """Ratio of Candidates that survived ranking to usable evidence.

    ``researched = total - excluded_degenerate`` (Invalid Candidates are a
    subset of Degenerate ones, so they are never subtracted twice). The
    misconfigured clause is appended only when the Invalid count is positive.
    """
    total = int(optimization.get("total", 0) or 0)
    excluded_degenerate = int(optimization.get("excluded_degenerate", 0) or 0)
    excluded_invalid = int(optimization.get("excluded_invalid", 0) or 0)
    researched = total - excluded_degenerate
    line = f"researched candidates: {researched}/{total}"
    if excluded_invalid > 0:
        line += f" ({excluded_invalid} misconfigured)"
    return line


def _metric_cell(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):+.3f}"
    except (TypeError, ValueError):
        return "n/a"


def report_summary(report: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    reasons = [
        clip_message(str(reason), max_chars=MAX_REASON_CHARS)
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
        return safe_path(value)
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

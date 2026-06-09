"""Pydantic v2 adapter: map ``ValidationError.errors()`` to ``ConfigValidationIssue``.

Also provides a ``removed_fields`` coordinator prepass that scans a raw section
dict for tombstoned keys, appends ``ConfigValidationIssue`` entries with the exact
bespoke message, and strips the keys before pydantic validation (so ``extra="forbid"``
doesn't double-emit an unknown-key error for the same field).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from research.aegis_research.configuration.schema import ConfigValidationIssue


def _validation_error_to_issues(
    error: ValidationError,
    *,
    section: str,
) -> list[ConfigValidationIssue]:
    """Map every pydantic ``ValidationError`` entry to a ``ConfigValidationIssue``.

    ``loc`` is joined with ``.`` (``[i]`` for int elements), prepended with the
    section name. The pydantic ``msg`` is taken verbatim — no translation table.
    """
    issues: list[ConfigValidationIssue] = []
    for entry in error.errors():
        loc = entry["loc"]
        path_parts: list[str] = [section]
        for part in loc:
            if isinstance(part, int):
                path_parts.append(f"[{part}]")
            else:
                path_parts.append(str(part))
        dotted = ".".join(path_parts)
        issues.append(ConfigValidationIssue(dotted, entry["msg"]))
    return issues


def _apply_removed_fields(
    raw: dict[str, Any],
    section: str,
    removed: dict[str, str],
    issues: list[ConfigValidationIssue],
) -> dict[str, Any]:
    """Scan *raw* for tombstoned keys, append issues with bespoke messages, and strip.

    This is a coordinator prepass, NOT a ``@model_validator``. A validator raising
    ``ValueError`` gives ``loc=()`` and ``msg='Value error, <text>'`` — it loses the
    dotted path and mangles the string.
    """
    stripped = dict(raw)
    for key, message in removed.items():
        if key in stripped:
            issues.append(ConfigValidationIssue(f"{section}.{key}", message))
            del stripped[key]
    return stripped

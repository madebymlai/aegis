"""Top-level ``lock:`` block validation.

A top-level ``lock: {run_id, candidate_id}`` reproduces one prior Candidate — its two
fields together are the ``candidates`` primary key ``(run_id, candidate_key)``. This
validator enforces the block shape only.

A config may carry both a top-level ``lock:`` and per-Component ``params:`` (lock-wins,
per ADR-0006): the locked Candidate's params take effect and the overridden ``params:``
values are recorded in the Run's Evidence — never silently dropped, never rejected. The
``params:`` values-only contract (manifest-declared names, secret-free, no run-executable
keys) is still enforced by the component-ref validator, independent of any ``lock:``.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import ConfigValidationIssue
from research.aegis_research.configuration.validation.base import (
    _require_str,
    _validate_known_keys,
)

_LOCK_ALLOWED_KEYS = {"run_id", "candidate_id"}


def _validate_lock(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    if raw.get("lock") is None:
        return
    value = raw["lock"]
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue("lock", "must be a mapping of run_id and candidate_id"))
        return
    _validate_known_keys("lock", value, _LOCK_ALLOWED_KEYS, issues)
    _require_str("lock.run_id", value, issues)
    _require_str("lock.candidate_id", value, issues)

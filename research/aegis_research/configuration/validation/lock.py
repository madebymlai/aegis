"""Top-level ``lock:`` block validation.

A top-level ``lock: {run_id, candidate_id}`` reproduces one prior Candidate — its two
fields together are the ``candidates`` primary key ``(run_id, candidate_key)``. This
validator enforces the block shape and the interim rule that a config carrying both a
top-level ``lock:`` and any per-Component ``params:`` is rejected (relaxed in the
follow-up slice).
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
    _validate_no_component_params(raw, issues)


def _validate_no_component_params(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    refs = [("strategy", raw.get("strategy"))]
    indicators = raw.get("indicators")
    if isinstance(indicators, list):
        refs.extend((f"indicators[{index}]", item) for index, item in enumerate(indicators))
    for path, ref in refs:
        if isinstance(ref, dict) and "params" in ref:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.params",
                    "must not be set when a top-level lock: is present; the lock reproduces "
                    "a whole Candidate (interim: lock and params: are mutually exclusive)",
                )
            )

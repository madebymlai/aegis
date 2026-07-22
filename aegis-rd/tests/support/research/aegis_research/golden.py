"""Golden-bytes comparison support (ADR-0003/0004 golden-bytes style).

``masked_canonical_manifest`` replaces a persisted Manifest's volatile fields
(wall-clock timestamps, host environment evidence) with fixed placeholders and
re-serializes the document in Canonical Form, so two Runs of the same config
on different machines produce identical bytes. Everything substantive — config
evidence, optimization evidence, and candidate rows — passes through
unmasked.

``assert_matches_golden`` compares those bytes against a committed golden
file. Regenerating a golden is a deliberate act::

    AERD_UPDATE_GOLDENS=1 uv run pytest <test>
"""

from __future__ import annotations

import difflib
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes

UPDATE_GOLDENS_ENV = "AERD_UPDATE_GOLDENS"
_MASKED = "<masked>"
_DIFF_CONTEXT_LINES = 3
_MAX_DIFF_CHARS = 6000


def masked_canonical_manifest(payload: dict[str, Any]) -> bytes:
    """Return the Manifest's Canonical Form bytes with volatile fields masked."""
    doc = deepcopy(payload)
    run = doc.get("run", {})
    for field in ("started_at", "finished_at"):
        if field in run:
            run[field] = _MASKED
    evidence = doc.get("evidence", {})
    if "environment" in evidence:
        evidence["environment"] = _MASKED
    # The config Evidence records the resolved absolute config path (ADR-0021);
    # absolute paths vary per run directory, so they mask like timestamps.
    config_evidence = evidence.get("config", {})
    if "source_path" in config_evidence:
        config_evidence["source_path"] = _MASKED
    selection = config_evidence.get("selection")
    if selection and "config_path" in selection:
        selection["config_path"] = _MASKED
    return canonical_json_bytes(doc, indent=2)


def assert_matches_golden(actual: bytes, golden_path: Path) -> None:
    """Compare ``actual`` byte-for-byte against the committed golden file.

    With ``AERD_UPDATE_GOLDENS=1`` the golden is (re)written instead of
    compared — the conscious regeneration path after an intended change.
    """
    if os.environ.get(UPDATE_GOLDENS_ENV) == "1":
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_bytes(actual)
        return
    if not golden_path.exists():
        raise AssertionError(
            f"golden file missing: {golden_path}\n"
            f"Generate it deliberately with {UPDATE_GOLDENS_ENV}=1 and commit it."
        )
    expected = golden_path.read_bytes()
    if actual == expected:
        return
    diff = "\n".join(
        difflib.unified_diff(
            expected.decode("utf-8").splitlines(),
            actual.decode("utf-8").splitlines(),
            fromfile=str(golden_path),
            tofile="actual (masked canonical manifest)",
            lineterm="",
            n=_DIFF_CONTEXT_LINES,
        )
    )
    raise AssertionError(
        "persisted Manifest bytes moved unexpectedly; if the change is "
        f"intended, regenerate with {UPDATE_GOLDENS_ENV}=1 and commit the "
        f"golden.\n{diff[:_MAX_DIFF_CHARS]}"
    )

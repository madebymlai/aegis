from __future__ import annotations

import hashlib
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.configuration import (
    ResolvedRunConfig,
    to_builtin,
)


def capture_config_evidence(config: ResolvedRunConfig) -> dict[str, Any]:
    evidence = {
        "schema_version": config.config.schema_version,
        "source_path": config.source_path,
        "authored_config_hash": canonical_hash(config.authored_config_document()),
        "resolved_config_hash": canonical_hash(config.resolved_config_document()),
        "raw_config_identity": {"hash": config.raw_config_hash},
    }
    if config.selection is not None:
        evidence["selection"] = dict(config.selection.manifest())
    return evidence


def canonical_hash(value: Any) -> str:
    json_safe_value = to_builtin(value)
    return hashlib.sha256(canonical_json_bytes(json_safe_value)).hexdigest()

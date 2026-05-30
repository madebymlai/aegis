from __future__ import annotations

import json
from typing import Any

_CANONICAL_JSON_SEPARATORS = (",", ":")

__all__ = ["canonical_json_bytes"]


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-safe value to stable UTF-8 JSON bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=_CANONICAL_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")

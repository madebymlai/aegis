from __future__ import annotations

import hashlib
import json
from typing import Any

_CANONICAL_JSON_SEPARATORS = (",", ":")
_DEFAULT_TOKEN_DIGEST_CHARS = 32


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-safe value to stable UTF-8 JSON bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=_CANONICAL_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any, *, chars: int = _DEFAULT_TOKEN_DIGEST_CHARS) -> str:
    """SHA-256 digest prefix over the canonical JSON byte representation."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()[:chars]


def mint_canonical_token(
    prefix: str,
    value: Any,
    *,
    chars: int = _DEFAULT_TOKEN_DIGEST_CHARS,
) -> str:
    """Mint a stable opaque token from a prefix and canonical JSON payload."""
    return f"{prefix}_{canonical_digest(value, chars=chars)}"

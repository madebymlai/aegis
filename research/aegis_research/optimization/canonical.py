from __future__ import annotations

import hashlib
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes

_DEFAULT_TOKEN_DIGEST_CHARS = 32


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
